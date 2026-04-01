import re

FILE_PATH = 'frontend/src/pages/admin/SotuvMijozlar.jsx'
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    code = f.read()

new_view = """/* ── Sale Create View ── */
function SaleCreateView({ customers, onBack, onSaved }) {
  const [products, setProds] = useState([]);
  
  useEffect(() => {
    api.get('/products/', { params: { limit: 200, status: 'active' } })
       .then(r => setProds(Array.isArray(r.data) ? r.data : (r.data.items||[]))).catch(()=>{});
  }, []);

  const [cart, setCart] = useState([]);
  const [custId, setCust] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const [showPay, setShowPay] = useState(false);
  const [payForm, setPayForm] = useState({ discType: 'amt', discVal: '', cash: '', info: '' });

  const totalNet = cart.reduce((s, c) => s + c.qty_ordered * c.net_cost, 0);

  const calcFinalTotal = () => {
    const d = Number(payForm.discVal) || 0;
    return payForm.discType === 'pct' ? totalNet * (1 - d / 100) : totalNet - d;
  };
  const finalTotal = calcFinalTotal();
  const paid = (Number(payForm.cash) || 0);
  const debt = Math.max(0, finalTotal - paid);
  const change = Math.max(0, paid - finalTotal);

  const doSave = async (paymentInfo = null) => {
    if (!cart.length) { setErr("Kamida bitta mahsulot qo'shing"); return; }
    setSaving(true); setErr('');
    try {
      const payload = {
        items: cart.map(c => ({ product_id: c.product_id, quantity: c.qty_ordered, unit_price: c.unit_price, discount: c.discount_val })),
        payment_type: 'cash',
        paid_amount: finalTotal,
        discount_amount: 0,
        note: note || '',
        customer_id: custId ? Number(custId) : null,
      };

      if (paymentInfo) {
         payload.paid_amount = paymentInfo.paid;
         payload.discount_amount = totalNet - finalTotal;
         payload.payment_type = 'cash';
         if (debt > 0 && paymentInfo.paid === 0) payload.payment_type = 'debt';
         else if (debt > 0) payload.payment_type = 'mixed';
         if (paymentInfo.info) payload.note = (payload.note ? payload.note + '\\n' : '') + paymentInfo.info;
      }

      await api.post('/sales', payload);
      onSaved(); onBack();
    } catch (e) { setErr(e.response?.data?.detail || 'Xatolik'); } finally { setSaving(false); }
  };

  const searchRef = useRef(null);
  const qtyRef = useRef(null);
  const [sel, setSel] = useState(null);
  const [qty, setQty] = useState('');
  const [price, setPrice] = useState('');
  const [discType, setDiscType] = useState('pct');
  const [discVal, setDiscVal] = useState('0');

  const selectProduct = (p) => {
    setSel(p);
    setPrice(String(Math.round(p.sale_price) || '0'));
    setQty(''); setDiscVal('0'); setDiscType('pct');
    setTimeout(() => { if (qtyRef.current) qtyRef.current.focus(); }, 10);
  };

  const calcNet = (rawPrice, dType, dVal) => {
    const p = Number(rawPrice) || 0;
    const d = Number(dVal) || 0;
    return dType === 'pct' ? p * (1 - d / 100) : p - d;
  };
  const selNet = calcNet(price, discType, discVal);

  const addItem = () => {
    if (!sel || !qty) return;
    const base = {
      product_id: sel.id, product_name: sel.name, unit: sel.unit || 'dona',
      unit_price: Number(price) || 0, discount_type: discType, discount_val: Number(discVal) || 0,
      net_cost: selNet,
    };
    setCart(prev => {
      const ex = prev.find(x => x.product_id === sel.id);
      if (ex) return prev.map(x => x.product_id === sel.id ? { ...x, qty_ordered: x.qty_ordered + Number(qty) } : x);
      return [...prev, { ...base, qty_ordered: Number(qty) }];
    });
    setSel(null); setQty(''); setPrice(''); setDiscVal('0');
    setTimeout(() => { if (searchRef.current) searchRef.current.focus(); }, 10);
  };

  const updCart = (i, field, val) => setCart(prev => prev.map((x, idx) => idx === i ? { ...x, [field]: val, net_cost: calcNet(field==='unit_price'?val:x.unit_price, field==='discount_type'?val:x.discount_type, field==='discount_val'?val:x.discount_val) } : x));

  return (
    <div className="fixed inset-0 z-40 bg-slate-50 flex flex-col">
      <div className="flex items-center gap-4 px-6 py-4 bg-white border-b border-slate-100 flex-shrink-0">
        <button onClick={onBack} className="inline-flex items-center gap-2 text-slate-500 hover:text-indigo-600 px-3 py-2 rounded-xl hover:bg-indigo-50 font-semibold">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" /></svg>Orqaga
        </button>
        <div className="w-px h-6 bg-slate-200" />
        <h1 className="text-xl font-bold text-slate-800">Yangi sotuv</h1>
        <div className="flex-1 flex gap-3 ml-4">
          <div className="w-64">
            <CustSearch customers={customers} value={custId} onChange={setCust} placeholder="Mijoz tanlang..." />
          </div>
          <input value={note} onChange={e => setNote(e.target.value)} placeholder="Izoh (ixtiyoriy)..." className="flex-1 max-w-sm border border-slate-200 rounded-xl px-4 text-sm focus:ring-2 focus:ring-indigo-400 outline-none" />
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <div className="w-[500px] border-r border-slate-100 p-6 flex flex-col gap-6 overflow-y-auto bg-white flex-shrink-0">
          <Lbl t="Mahsulot qidirish">
            <ProdSearch products={products} onSelect={selectProduct} inputRef={searchRef} />
          </Lbl>

          {sel ? (
            <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-5 space-y-4">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-indigo-600 text-white flex items-center justify-center text-sm font-bold shadow-sm">
                  {sel.name.slice(0,2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-slate-800 text-base truncate">{sel.name}</div>
                  <div className="text-sm text-slate-600 mt-1">Qoldiq: <strong>{fmt(sel.stock_quantity)}</strong> {sel.unit||'dona'}</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 pt-2 border-t border-indigo-100/50">
                <Lbl t="Soni*">
                  <div className="flex items-center bg-white border border-slate-200 rounded-xl overflow-hidden focus-within:ring-2 focus-within:ring-indigo-500 shadow-sm">
                    <input type="number" min="1" step="any" value={qty} onChange={e=>setQty(e.target.value)} ref={qtyRef} onKeyDown={e=>e.key==='Enter'&&addItem()} className="flex-1 w-full py-2.5 px-3 text-lg font-bold text-center outline-none" placeholder="0" />
                    <div className="px-3 py-2.5 bg-slate-50 border-l border-slate-200 text-slate-500 font-semibold text-sm">{sel.unit||'dona'}</div>
                  </div>
                </Lbl>
                <Lbl t="Sotish narxi*">
                  <div className="flex items-center bg-white border border-slate-200 rounded-xl overflow-hidden focus-within:ring-2 focus-within:ring-indigo-500 shadow-sm">
                    <input type="number" min="0" value={price} onChange={e=>setPrice(e.target.value)} onKeyDown={e=>e.key==='Enter'&&addItem()} className="flex-1 w-full py-2.5 px-3 text-lg font-bold text-center outline-none" />
                  </div>
                </Lbl>
                <Lbl t="Chegirma" className="col-span-2">
                  <div className="flex items-center bg-white border border-slate-200 rounded-xl overflow-hidden focus-within:ring-2 focus-within:ring-indigo-500 shadow-sm h-11">
                    <input type="number" min="0" value={discVal} onChange={e=>setDiscVal(e.target.value)} onKeyDown={e=>e.key==='Enter'&&addItem()} className="flex-1 py-2 px-3 text-base font-bold text-center outline-none" />
                    <button onClick={()=>setDiscType(t=>t==='pct'?'amt':'pct')} className={`w-14 h-full flex items-center justify-center font-bold border-l border-slate-200 transition-colors ${discType==='pct'?'bg-amber-100 text-amber-700':'bg-violet-100 text-violet-700'}`}>{discType==='pct'?'%':"so'm"}</button>
                  </div>
                </Lbl>
              </div>

              <div className="flex items-end justify-between pt-4 pb-2">
                <div className="text-sm text-slate-500 font-medium">Sof narx:</div>
                <div className="text-xl font-black text-emerald-600">{fmt(Math.round(selNet))} UZS</div>
              </div>
              <button onClick={addItem} disabled={!qty || Number(qty)<=0} className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold rounded-xl transition-all shadow-md active:scale-95">
                Ro'yxatga qo'shish
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center flex-1 text-slate-300 gap-3">
              <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
              <p>Mahsulot tanlang</p>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto">
          {cart.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-300 flex-col gap-2"><svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg><p>Mahsulot qo'shing</p></div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 z-10">
                <tr>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 w-8">№</th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-slate-500 uppercase">Mahsulot</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-24">Soni</th>
                  <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-32">Narxi</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-28">Chegirma</th>
                  <th className="text-right px-3 py-3 text-xs font-semibold text-slate-500 uppercase w-32">Sof narx</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase w-32">Jami</th>
                  <th className="w-8"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {cart.map((it, i) => (
                  <tr key={i} className="hover:bg-slate-50 group">
                    <td className="px-4 py-3 text-slate-400 text-xs">{i+1}</td>
                    <td className="px-3 py-3">
                      <div className="font-semibold text-slate-800">{it.product_name}</div>
                      <div className="text-xs text-slate-400">{it.unit}</div>
                    </td>
                    <td className="px-3 py-3 text-center">
                      <input type="number" min="0.1" step="any" value={it.qty_ordered} onChange={e=>updCart(i,'qty_ordered',Number(e.target.value))} className="w-16 text-center border border-slate-200 rounded-lg py-1.5 focus:ring-2 focus:ring-indigo-500 font-bold" />
                    </td>
                    <td className="px-3 py-3 text-right">
                      <input type="number" min="0" value={it.unit_price} onChange={e=>updCart(i,'unit_price',e.target.value)} className="w-24 text-right border border-slate-200 rounded-lg py-1.5 px-2 focus:ring-2 focus:ring-indigo-500" />
                    </td>
                    <td className="px-3 py-3 text-center">
                      <div className="flex items-center justify-center gap-1">
                        <input type="number" min="0" value={it.discount_val} onChange={e=>updCart(i,'discount_val',e.target.value)} className="w-16 text-center border border-slate-200 rounded-lg py-1.5 focus:ring-2 focus:ring-indigo-500" />
                        <button onClick={()=>updCart(i,'discount_type',it.discount_type==='pct'?'amt':'pct')} className={`text-[10px] font-bold px-1.5 py-1.5 rounded-md transition-colors ${it.discount_type==='pct'?'bg-amber-100 text-amber-700':'bg-violet-100 text-violet-700'}`}>{it.discount_type==='pct'?'%':"so'm"}</button>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-right font-bold text-emerald-600">{fmt(Math.round(it.net_cost))}</td>
                    <td className="px-4 py-3 text-right font-black text-slate-800">{fmt(Math.round(it.net_cost * it.qty_ordered))}</td>
                    <td className="pr-3">
                      <button onClick={()=>setCart(p=>p.filter((_,idx)=>idx!==i))} className="p-1.5 text-slate-300 hover:text-red-500 rounded opacity-0 group-hover:opacity-100 transition-opacity">✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200 bg-white flex-shrink-0">
        <div className="flex gap-3">
          <Btn v="ghost" onClick={onBack}>Bekor qilish</Btn>
          {err && <span className="text-red-500 font-bold bg-red-50 px-3 py-1.5 rounded-xl border border-red-100">{err}</span>}
        </div>
        <div className="flex gap-3 items-center">
          {cart.length > 0 && <span className="mr-3 font-bold text-slate-500">Jami summasi: <span className="text-slate-800 text-lg ml-1">{fmt(totalNet)} UZS</span></span>}
          <button onClick={()=>{ if(!cart.length){setErr("Savat bo'sh"); return;} setErr(''); setShowPay(true); }} className="px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold shadow-sm flex items-center gap-2">
            To'lov
          </button>
        </div>
      </div>

      {showPay && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/60 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-3xl flex flex-col max-h-full animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between px-6 py-5 border-b border-slate-100">
              <h2 className="text-xl font-bold text-slate-800 tracking-tight">Kassadan to'lov <span className="text-blue-500 font-medium ml-2">{new Date().toLocaleString('uz-UZ').replace(',', '')}</span></h2>
              <button onClick={()=>setShowPay(false)} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-slate-100 text-slate-400 transition-colors bg-slate-50 border border-slate-200">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            <div className="p-8 overflow-y-auto space-y-8 bg-slate-50/50">
              <div className="grid grid-cols-2 gap-8">
                <div className="space-y-3">
                  <div className="flex items-center gap-4 text-sm font-bold text-slate-600 uppercase tracking-widest">
                    Chegirma (Savatga)
                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-500 normal-case hover:text-slate-700"><input type="radio" checked={payForm.discType==='amt'} onChange={()=>setPayForm(p=>({...p,discType:'amt'}))} className="w-4 h-4 text-blue-600" /> Foizsiz</label>
                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-500 normal-case hover:text-slate-700"><input type="radio" checked={payForm.discType==='pct'} onChange={()=>setPayForm(p=>({...p,discType:'pct'}))} className="w-4 h-4 text-blue-600" /> %</label>
                  </div>
                  <div className="flex h-14 bg-white rounded-xl shadow-sm border-2 border-slate-200 focus-within:border-blue-500 focus-within:ring-4 focus-within:ring-blue-500/20">
                    <input type="number" value={payForm.discVal} onChange={e=>setPayForm(p=>({...p,discVal:e.target.value}))} className="flex-1 border-none bg-transparent px-4 text-xl font-bold rounded-l-xl outline-none" placeholder="0" />
                    <div className="bg-slate-50 px-5 flex items-center border-l border-slate-100 text-slate-500 text-sm font-bold rounded-r-xl">UZS | 1</div>
                  </div>
                </div>

                <div className="space-y-3">
                  <label className="text-sm font-bold text-slate-600 uppercase tracking-widest">Kassa</label>
                  <select className="w-full h-14 bg-white border-2 border-slate-200 rounded-xl px-4 text-lg font-bold shadow-sm outline-none">
                    <option value="1">KASSA</option>
                  </select>
                </div>

                <div className="space-y-3 col-span-2">
                  <label className="text-sm font-bold text-slate-600 uppercase tracking-widest">To'lov qiymati (so'm)</label>
                  <div className="flex gap-2 h-14 items-center">
                    <div className="bg-white px-5 flex items-center border border-slate-200 rounded-xl text-sm font-bold text-slate-600 h-full shadow-sm">Kassa (Naqd)</div>
                    <div className="flex flex-1 items-center h-full rounded-xl focus-within:ring-4 focus-within:ring-blue-500/20 focus-within:border-blue-500 border-2 border-slate-200 bg-white shadow-sm overflow-hidden">
                      <input type="number" min="0" value={payForm.cash} onChange={e=>setPayForm(p=>({...p,cash:e.target.value}))} className="flex-1 w-full h-full border-none px-4 text-2xl font-black text-slate-800 outline-none bg-transparent" placeholder="0" />
                      <div className="px-4 flex items-center text-blue-600 text-sm font-bold h-full border-l border-slate-100 bg-slate-50">UZS</div>
                      <button onClick={()=>setPayForm(p=>({...p, cash: String(Math.round(finalTotal))}))} className="bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold px-6 h-full border-l border-slate-200 text-sm whitespace-nowrap">Umumiy Summa</button>
                    </div>
                  </div>
                </div>

                <div className="space-y-3 col-span-2">
                  <textarea rows="2" value={payForm.info} onChange={e=>setPayForm(p=>({...p,info:e.target.value}))} className="w-full border-2 border-slate-200 rounded-xl p-4 text-sm resize-none focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20" placeholder="Ma'lumot..."></textarea>
                </div>
              </div>

              <div className="flex flex-col items-end gap-3 pt-6 border-t border-slate-200">
                <div className="flex items-center justify-between w-80 text-lg"><span className="text-slate-500 font-semibold text-sm uppercase tracking-wide">Umumiy summa:</span><span className="font-black text-emerald-600 bg-emerald-50 px-3 py-1 rounded-xl">{fmt(Math.round(finalTotal))}</span></div>
                <div className="flex items-center justify-between w-80 text-lg"><span className="text-slate-500 font-semibold text-sm uppercase tracking-wide">To'lov:</span><span className="font-bold text-blue-700 bg-blue-100/50 border border-blue-200 px-3 py-1.5 rounded-xl">{fmt(Math.round(paid))} UZS</span></div>
                {debt > 0 && <div className="flex items-center justify-between w-80 text-lg animate-in slide-in-from-right-2"><span className="text-slate-500 font-semibold text-sm uppercase tracking-wide">Qarzga:</span><span className="font-bold text-red-600 bg-red-50 border border-red-200 px-3 py-1.5 rounded-xl">{fmt(Math.round(debt))}</span></div>}
                {change > 0 && <div className="flex items-center justify-between w-80 text-lg animate-in slide-in-from-right-2"><span className="text-slate-500 font-semibold text-sm uppercase tracking-wide">Qaytim:</span><span className="font-bold text-slate-600 bg-slate-100 border border-slate-200 px-3 py-1.5 rounded-xl">{fmt(Math.round(change))}</span></div>}
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 px-6 py-5 border-t border-slate-100 bg-white mt-auto rounded-b-2xl">
              <button onClick={()=>setShowPay(false)} className="px-6 py-3.5 rounded-xl border border-slate-200 text-slate-600 font-bold hover:bg-slate-50 hover:text-slate-900 transition-all text-sm">Bekor qilish</button>
              <button disabled={saving} onClick={() => doSave({ paid: paid > finalTotal ? finalTotal : paid, info: payForm.info })} className="px-8 py-3.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-black text-sm shadow-md flex items-center gap-2 transition-all active:scale-95">
                {saving ? '...' : <><svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7"/></svg>Sotuvni yakunlash</>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
"""

pattern = r'function SaleCreateView\(\{ customers, onBack, onSaved \}\) \{[\s\S]*?(?=function SaleDetailModal)'

if re.search(pattern, code):
    new_code = re.sub(pattern, new_view + '\n\n', code)
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(new_code)
    print("SUCCESS: Code replaced.")
else:
    print("ERROR: Pattern not found.")
