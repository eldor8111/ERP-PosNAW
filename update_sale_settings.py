import re

SOTUV_PATH = 'frontend/src/pages/admin/SotuvMijozlar.jsx'

with open(SOTUV_PATH, 'r', encoding='utf-8') as f:
    code = f.read()

HEADER_OLD = """  return (
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
      </div>"""

HEADER_NEW = """  // POS Settings (stored in localStorage)
  const [showSettings, setShowSettings] = useState(false);
  const [posSettings, setPosSettings] = useState(() => {
    try { return JSON.parse(localStorage.getItem('pos_settings') || '{}'); } catch { return {}; }
  });
  const savePosSettings = (updates) => {
    const next = { ...posSettings, ...updates };
    setPosSettings(next);
    localStorage.setItem('pos_settings', JSON.stringify(next));
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-50 flex flex-col">
      <div className="flex items-center gap-4 px-6 py-4 bg-white border-b border-slate-100 flex-shrink-0">
        <button onClick={onBack} className="inline-flex items-center gap-2 text-slate-500 hover:text-indigo-600 px-3 py-2 rounded-xl hover:bg-indigo-50 font-semibold">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" /></svg>Orqaga
        </button>
        <div className="w-px h-6 bg-slate-200" />
        <h1 className="text-xl font-bold text-slate-800">Yangi sotuv</h1>
        <div className="flex-1 flex gap-3 ml-4 items-center">
          <div className="w-64">
            <CustSearch customers={customers} value={custId} onChange={setCust} placeholder={posSettings.require_customer ? 'Mijoz KERAK  ★...' : 'Mijoz tanlang...'} />
          </div>
          <input value={note} onChange={e => setNote(e.target.value)} placeholder="Izoh (ixtiyoriy)..." className="flex-1 max-w-sm border border-slate-200 rounded-xl px-4 text-sm focus:ring-2 focus:ring-indigo-400 outline-none" />
        </div>
        {/* Settings Gear */}
        <button onClick={() => setShowSettings(s => !s)} title="Nastroykalar"
          className={`ml-auto w-10 h-10 rounded-xl flex items-center justify-center border transition-all flex-shrink-0 ${showSettings ? 'bg-indigo-600 text-white border-indigo-600 shadow-md' : 'bg-slate-50 text-slate-500 border-slate-200 hover:bg-indigo-50 hover:text-indigo-600'}`}>
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
        </button>
      </div>

      {/* ─── Settings Panel ─── */}
      {showSettings && (
        <div className="bg-white border-b border-indigo-100 px-8 py-5 shadow-sm flex flex-wrap gap-8 items-start">
          <div className="text-sm font-black text-slate-700 uppercase tracking-widest self-center">⚙ Sotuv nastroykalar</div>

          {/* Toggle helper */}
          {[ 
            { key: 'require_customer',   label: "Mijoz tanlanmasa ruxsat berma", desc: "Tovar qo'shishdan oldin mijoz tanlanishi shart" },
            { key: 'allow_negative',     label: "Minusga sotishga ruxsat",        desc: "Qoldig'i 0 bo'lsa ham sotish mumkin" },
            { key: 'always_wholesale',   label: "Har doim ulgurji narx",          desc: "Ulgurji narx bo'yicha sotuv" },
          ].map(opt => (
            <label key={opt.key} className="flex items-start gap-3 cursor-pointer group min-w-52">
              <div className="mt-0.5">
                <div onClick={() => savePosSettings({ [opt.key]: !posSettings[opt.key] })}
                  className={`w-11 h-6 rounded-full flex items-center px-0.5 transition-colors cursor-pointer flex-shrink-0 ${posSettings[opt.key] ? 'bg-indigo-600' : 'bg-slate-200'}`}>
                  <div className={`w-5 h-5 rounded-full bg-white shadow transition-transform ${posSettings[opt.key] ? 'translate-x-5' : 'translate-x-0'}`} />
                </div>
              </div>
              <div>
                <div className="text-sm font-semibold text-slate-700 group-hover:text-indigo-700">{opt.label}</div>
                <div className="text-xs text-slate-400 mt-0.5">{opt.desc}</div>
              </div>
            </label>
          ))}

          {/* Max discount */}
          <div className="flex flex-col gap-1 min-w-40">
            <label className="text-xs font-bold text-slate-600 uppercase tracking-widest">Maks. chegirma (%)</label>
            <div className="flex items-center gap-2">
              <input type="number" min="0" max="100" value={posSettings.max_discount ?? ''} placeholder="Cheksiz"
                onChange={e => savePosSettings({ max_discount: e.target.value === '' ? null : Number(e.target.value) })}
                className="w-24 border border-slate-200 rounded-xl px-3 py-2 text-sm text-center font-bold focus:ring-2 focus:ring-indigo-400 outline-none" />
              <span className="text-slate-400 text-sm font-bold">%</span>
            </div>
          </div>

          {/* Default kassa label */}
          <div className="flex flex-col gap-1 min-w-36">
            <label className="text-xs font-bold text-slate-600 uppercase tracking-widest">Standart Kassa</label>
            <input type="text" value={posSettings.kassa_name ?? ''} placeholder="Kassa nomi..."
              onChange={e => savePosSettings({ kassa_name: e.target.value })}
              className="border border-slate-200 rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-400 outline-none" />
          </div>
        </div>
      )}
"""

if 'showSettings' not in code:
    if HEADER_OLD in code:
        code = code.replace(HEADER_OLD, HEADER_NEW)
        print("Settings gear injected successfully.")
    else:
        # Try partial match
        idx = code.find('<h1 className="text-xl font-bold text-slate-800">Yangi sotuv</h1>')
        print(f"Header find at idx={idx}")
        print(repr(code[idx-200:idx+300]))
else:
    print("Settings already injected.")

with open(SOTUV_PATH, 'w', encoding='utf-8') as f:
    f.write(code)
print("SotuvMijozlar.jsx updated.")
