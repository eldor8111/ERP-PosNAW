import re

with open(r"d:\ERP-PosNAW\frontend\src\pages\admin\Products.jsx", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add BulkStockEditModal component before export default function Products()
bulk_stock_modal_code = """
/* ─── BulkStockEditModal (Massoviy Revizya) ─────────────────── */
function BulkStockEditModal({ selectedIds, products, warehouses, onClose, onSuccess }) {
  const { t } = useLang();
  const [warehouseId, setWarehouseId] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  
  // Faqat hozirgi sahifada bor bo'lgan va tanlangan mahsulotlarni ajratib olamiz
  const [items, setItems] = useState(() => {
    return products
      .filter(p => selectedIds.includes(p.id))
      .map(p => ({
        product: p,
        fact: '',
        reason: ''
      }));
  });

  const doSave = async () => {
    if (!warehouseId) { setErr("Omborni tanlang!"); return; }
    const validItems = items.filter(i => i.fact !== '');
    if (!validItems.length) { setErr("Kamida bitta mahsulot uchun yangi qoldiq kiriting!"); return; }
    
    setSaving(true); setErr('');
    try {
      // 1. Create draft count
      const { data: count } = await api.post('/inventory-counts', {
        warehouse_id: Number(warehouseId),
        note: note || 'Tezkor qoldiq tahrirlash',
        category_ids: null
      });
      // 2. Start
      await api.post(`/inventory-counts/${count.id}/start`);
      // 3. Update items
      const itemsPayload = validItems.map(c => ({
        product_id: c.product.id,
        counted_qty: Number(c.fact),
        variance_reason: c.reason || null
      }));
      await api.post(`/inventory-counts/${count.id}/items`, itemsPayload);
      // 4. Finalize
      await api.post(`/inventory-counts/${count.id}/finalize`);
      
      toast.success("Qoldiq muvaffaqiyatli yangilandi");
      onSuccess();
    } catch (e) {
      setErr(e.response?.data?.detail || "Saqlashda xatolik yuz berdi");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={`Tanlangan mahsulotlar qoldig'ini tahrirlash (${selectedIds.length} ta)`} onClose={onClose} size="lg">
      <div className="p-5 flex flex-col gap-5">
        {selectedIds.length > items.length && (
          <div className="bg-amber-50 text-amber-700 p-3 rounded-xl text-sm font-medium flex items-center gap-2">
            <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            Siz boshqa sahifalardan ham mahsulot tanlagansiz. Hozir faqat shu sahifadagi {items.length} ta mahsulot ko'rsatilmoqda.
          </div>
        )}
        
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1">
            <label className="block text-sm font-semibold text-slate-600 mb-1.5">Ombor tanlang *</label>
            <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)} className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white">
              <option value="">— Ombor tanlang —</option>
              {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-sm font-semibold text-slate-600 mb-1.5">Izoh (ixtiyoriy)</label>
            <input value={note} onChange={e => setNote(e.target.value)} placeholder="Tuzatish sababi..." className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white" />
          </div>
        </div>

        <div className="border border-slate-200 rounded-xl overflow-hidden max-h-[50vh] overflow-y-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10">
              <tr>
                <th className="px-4 py-3 font-semibold text-slate-500">Mahsulot</th>
                <th className="px-4 py-3 font-semibold text-slate-500 w-32 text-center">Tizim qoldig'i</th>
                <th className="px-4 py-3 font-semibold text-slate-500 w-40">Yangi (Faktik) qoldiq</th>
                <th className="px-4 py-3 font-semibold text-slate-500 w-48">Tafovut sababi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((it, idx) => (
                <tr key={it.product.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-slate-800">{it.product.name}</td>
                  <td className="px-4 py-3 text-center text-slate-500 bg-slate-50/50">{it.product.stock_quantity || 0} {it.product.unit || 'dona'}</td>
                  <td className="px-4 py-2">
                    <input type="number" min="0" step="any" value={it.fact}
                      onChange={e => {
                        const val = e.target.value;
                        setItems(prev => prev.map((p, i) => i === idx ? { ...p, fact: val } : p));
                      }}
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 font-bold"
                      placeholder="0"
                    />
                  </td>
                  <td className="px-4 py-2">
                    <input type="text" value={it.reason}
                      onChange={e => {
                        const val = e.target.value;
                        setItems(prev => prev.map((p, i) => i === idx ? { ...p, reason: val } : p));
                      }}
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      placeholder="Sabab..."
                    />
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-slate-500">Hech qanday mahsulot topilmadi</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {err && <div className="text-red-500 text-sm font-medium text-center">{err}</div>}
        
        <div className="flex justify-end gap-3 pt-2">
          <button onClick={onClose} className="px-5 py-2.5 text-sm font-semibold border border-slate-200 text-slate-600 rounded-xl hover:bg-slate-50 transition-colors">Bekor qilish</button>
          <button onClick={doSave} disabled={saving || !items.some(i => i.fact !== '')} className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold rounded-xl shadow-sm transition-all">
            {saving ? 'Saqlanmoqda...' : 'Saqlash va Yakunlash'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/* ═══════════════════════════════════════════════════ */
export default function Products() {"""

content = content.replace("/* ═══════════════════════════════════════════════════ */\nexport default function Products() {", bulk_stock_modal_code)

# 2. Add bulkStockModal state
state_code = """  const [deletePercent, setDeletePercent] = useState(0);
  const [bulkDeleteModal, setBulkDeleteModal] = useState(null); // { code, entered }
  const [bulkStockModal, setBulkStockModal] = useState(false);
  const [massActionsOpen, setMassActionsOpen] = useState(false);"""
content = content.replace("  const [deletePercent, setDeletePercent] = useState(0);\n  const [bulkDeleteModal, setBulkDeleteModal] = useState(null); // { code, entered }", state_code)

# 3. Replace the delete button with Mass Actions dropdown
delete_btn_code_orig = """            ) : selectedIds.length > 0 && (
              <button onClick={handleBulkDelete} className="px-4 py-2.5 bg-red-50 hover:bg-red-100 text-red-600 text-sm font-semibold rounded-xl transition-colors inline-flex items-center gap-2 shrink-0">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                {selectedIds.length} {t('common.delete')}
              </button>
            )}"""

delete_btn_code_new = """            ) : selectedIds.length > 0 && (
              <div className="relative">
                <button onClick={() => setMassActionsOpen(o => !o)} className="px-4 py-2.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-sm font-semibold rounded-xl transition-colors inline-flex items-center gap-2 shrink-0">
                  Ommaviy amallar ({selectedIds.length})
                  <svg className={`w-4 h-4 transition-transform ${massActionsOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" /></svg>
                </button>
                {massActionsOpen && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setMassActionsOpen(false)} />
                    <div className="absolute top-full mt-2 left-0 w-56 bg-white rounded-xl shadow-xl border border-slate-100 z-20 py-1.5 overflow-hidden">
                      <button onClick={() => { setMassActionsOpen(false); setBulkStockModal(true); }} className="w-full text-left px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-indigo-50 hover:text-indigo-600 transition-colors flex items-center gap-2">
                        <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>
                        Qoldiqni tahrirlash
                      </button>
                      <div className="border-t border-slate-100 my-1.5" />
                      <button onClick={() => { setMassActionsOpen(false); handleBulkDelete(); }} className="w-full text-left px-4 py-2.5 text-sm font-semibold text-red-600 hover:bg-red-50 transition-colors flex items-center gap-2">
                        <svg className="w-4 h-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                        O'chirish
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}"""
content = content.replace(delete_btn_code_orig, delete_btn_code_new)

# 4. Render BulkStockEditModal
modal_render_orig = """      {bulkDeleteModal && (
        <Modal title={t('product.bulkDeleteTitle') || "Ommaviy o'chirish"} onClose={() => setBulkDeleteModal(null)} size="sm">"""

modal_render_new = """      {bulkStockModal && (
        <BulkStockEditModal
          selectedIds={selectedIds}
          products={products}
          warehouses={warehouses}
          onClose={() => setBulkStockModal(false)}
          onSuccess={() => {
            setBulkStockModal(false);
            setSelectedIds([]);
            loadProducts();
          }}
        />
      )}

      {bulkDeleteModal && (
        <Modal title={t('product.bulkDeleteTitle') || "Ommaviy o'chirish"} onClose={() => setBulkDeleteModal(null)} size="sm">"""
content = content.replace(modal_render_orig, modal_render_new)

with open(r"d:\ERP-PosNAW\frontend\src\pages\admin\Products.jsx", "w", encoding="utf-8") as f:
    f.write(content)
