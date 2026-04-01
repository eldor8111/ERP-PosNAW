FILE_PATH = 'frontend/src/pages/admin/SotuvMijozlar.jsx'
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    text = f.read()

lbl_code = """function Lbl({ className = '', t, children }) {
  return (
    <div className={className}>
      {t && <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">{t}</div>}
      {children}
    </div>
  );
}
"""

if 'function Lbl(' not in text:
    text = text.replace('/* ── Sale Create View ── */', lbl_code + '\n/* ── Sale Create View ── */')
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(text)
    print('Lbl injected')
else:
    print('Lbl already exists')
