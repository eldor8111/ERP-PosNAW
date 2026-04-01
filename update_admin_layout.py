import re
import os

FILE_PATH = 'frontend/src/components/AdminLayout.jsx'

with open(FILE_PATH, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Remove Mobile Menu
mobile_pattern = r'''\s*\{\s*name:\s*"Mobil Ko'rinish",\s*path:\s*'/admin/mobile',[\s\S]*?\},'''
text = re.sub(mobile_pattern, '', text)

# 2. Add API import and fmt import if not exists
if "import api from '../api/axios';" not in text:
    text = text.replace("import { useAuth }", "import api from '../api/axios';\nimport { useAuth }")
if "import { useEffect, useState } from 'react';" not in text:
    text = text.replace("import { useState } from 'react';", "import { useState, useEffect } from 'react';")

# formatting function
if "const fmt = " not in text:
    fmt_func = "\nconst fmt = (n) => Number(n || 0).toLocaleString('ru-RU');\n"
    text = text.replace('export default function AdminLayout() {', fmt_func + '\nexport default function AdminLayout() {')

# 3. Add state and useEffect inside AdminLayout
state_code = """
  const [orgData, setOrgData] = useState({ name: user?.company_name || 'Tizim', code: '...', balance: 0 });

  useEffect(() => {
    api.get('/finance/cash-balance').then(r => {
      setOrgData({
        name: r.data.company_name || 'Tizim',
        code: r.data.org_code || '-',
        balance: r.data.balance || 0
      });
    }).catch(e => console.error(e));
  }, []);
"""

if 'const [orgData' not in text:
    text = text.replace('const [collapsed, setCollapsed] = useState(false);', 'const [collapsed, setCollapsed] = useState(false);\n' + state_code)

# 4. Replace Header HTML
header_old_pattern = r'''\{user\?\.company_name && \([\s\S]*?\)\}'''

header_new = '''
            <div className="flex items-center gap-1.5 bg-indigo-50 border border-indigo-100 rounded-xl px-3 py-1.5 shadow-sm">
              <div className="flex flex-col text-right">
                <span className="text-indigo-800 text-[11px] font-black uppercase tracking-wider leading-none mb-0.5">{orgData.name} <span className="text-indigo-400 ml-1">#{orgData.code}</span></span>
                <span className="text-indigo-600 text-[10px] font-bold tracking-widest leading-none">Balans: <span className="text-emerald-600 ml-0.5">{fmt(orgData.balance)} s</span></span>
              </div>
              <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center text-indigo-500 ml-2">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>
              </div>
            </div>
'''
if '{orgData.name}' not in text:
    text = re.sub(header_old_pattern, header_new, text)

with open(FILE_PATH, 'w', encoding='utf-8') as f:
    f.write(text)
print("AdminLayout updated.")
