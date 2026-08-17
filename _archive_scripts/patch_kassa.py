import sys

file_path = "frontend/src/pages/admin/PosKassa.jsx"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add variantParent state
content = content.replace(
    "const [activeCat, setActiveCat] = useState(null);",
    "const [activeCat, setActiveCat] = useState(null);\n  const [variantParent, setVariantParent] = useState(null);"
)

# 2. Update filteredProducts to hide variants
content = content.replace(
    "const mc = activeCat ? p.category_id === activeCat : true;",
    "const mc = activeCat ? p.category_id === activeCat : true;\n    const mv = p.product_type !== 'variant';"
)
content = content.replace(
    "return ms && mc;",
    "return ms && mc && mv;"
)

# 3. Update addToCart to handle parent products
content = content.replace(
    "const addToCart = (p) => {",
    "const addToCart = (p) => {\n    if (p.product_type === 'parent') {\n      setVariantParent(p);\n      return;\n    }"
)

# 4. Add the VariantSelectorModal JSX before the final closing div
modal_jsx = """
      {variantParent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white w-full max-w-2xl rounded-3xl shadow-2xl flex flex-col max-h-[85vh] overflow-hidden">
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h2 className="text-xl font-black text-slate-800">{variantParent.name} - Variantlar</h2>
              <button onClick={() => setVariantParent(null)} className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-xl transition-colors">
                <X className="w-6 h-6" />
              </button>
            </div>
            <div className="p-6 overflow-y-auto grid grid-cols-2 sm:grid-cols-3 gap-4">
              {products.filter(p => p.parent_code === variantParent.id).map(v => {
                const size = v.attributes?.find(a => a.key === 'Size' || a.key === "O'lcham")?.value || '';
                const color = v.attributes?.find(a => a.key === 'Color' || a.key === 'Rang')?.value || '';
                const label = [size, color].filter(Boolean).join(' | ') || v.name;
                return (
                  <button key={v.id} onClick={() => { addToCart(v); setVariantParent(null); }} className="p-4 border border-slate-200 rounded-2xl hover:border-indigo-400 hover:bg-indigo-50 hover:shadow-lg transition-all text-left flex flex-col gap-2 group">
                    <span className="font-bold text-slate-700 group-hover:text-indigo-700">{label}</span>
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-bold text-indigo-600">{Number(v.sale_price).toLocaleString()} UZS</span>
                      <span className="text-slate-500">{v.stock_quantity || 0} {v.unit}</span>
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

print("PosKassa patched!")
