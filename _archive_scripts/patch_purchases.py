import sys

file_path = "frontend/src/pages/admin/Purchases.jsx"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add variantParent state
content = content.replace(
    "const [supplierModal, setSupplierModal] = useState(false);",
    "const [supplierModal, setSupplierModal] = useState(false);\n  const [variantParent, setVariantParent] = useState(null);"
)

# 2. Update filteredProducts to hide variants
content = content.replace(
    "const matches = p.name.toLowerCase().includes(q) || (p.sku && p.sku.toLowerCase().includes(q)) || (p.barcode && p.barcode.includes(q));",
    "const matches = (p.name.toLowerCase().includes(q) || (p.sku && p.sku.toLowerCase().includes(q)) || (p.barcode && p.barcode.includes(q))) && p.product_type !== 'variant';"
)

# 3. Update addProduct logic to open variant modal for parent products
content = content.replace(
    "const addProduct = (p) => {",
    "const addProduct = (p) => {\n    if (p.product_type === 'parent') {\n      setVariantParent(p);\n      return;\n    }"
)

# 4. Add the VariantSelectorModal JSX before the final closing div
modal_jsx = """
      {variantParent && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white w-full max-w-2xl rounded-3xl shadow-2xl flex flex-col max-h-[85vh] overflow-hidden">
            <div className="flex items-center justify-between p-6 border-b border-emerald-100">
              <h2 className="text-xl font-black text-slate-800">{variantParent.name} - Variantlar (Kirim qilish)</h2>
              <button onClick={() => setVariantParent(null)} className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-xl transition-colors">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="p-6 overflow-y-auto grid grid-cols-2 sm:grid-cols-3 gap-4">
              {products.filter(p => p.parent_code === variantParent.id).map(v => {
                const size = v.attributes?.find(a => a.key === 'Size' || a.key === "O'lcham")?.value || '';
                const color = v.attributes?.find(a => a.key === 'Color' || a.key === 'Rang')?.value || '';
                const label = [size, color].filter(Boolean).join(' | ') || v.name;
                return (
                  <button key={v.id} onClick={() => { addProduct(v); setVariantParent(null); }} className="p-4 border border-emerald-200 rounded-2xl hover:border-emerald-500 hover:bg-emerald-50 hover:shadow-lg transition-all text-left flex flex-col gap-2 group">
                    <span className="font-bold text-slate-700 group-hover:text-emerald-700">{label}</span>
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-bold text-emerald-600">{Number(v.cost_price).toLocaleString()} UZS (Tan)</span>
                      <span className="text-slate-500">Qoldiq: {v.stock_quantity || 0}</span>
                    </div>
                  </button>
                );
              })}
              {products.filter(p => p.parent_code === variantParent.id).length === 0 && (
                <div className="col-span-full py-8 text-center text-slate-400">Ushbu mahsulotning variantlari topilmadi</div>
              )}
            </div>
          </div>
        </div>
      )}
"""

# Find the last </div>
last_div_idx = content.rfind("</div>")
if last_div_idx != -1:
    content = content[:last_div_idx] + modal_jsx + "\n" + content[last_div_idx:]

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Purchases patched!")
