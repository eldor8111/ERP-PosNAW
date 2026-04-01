import shutil

src = 'c:/Users/ELDORBEK ABDUALIMOV/Desktop/ERPPos/frontend/src/pages/admin/PosDesktop.jsx'
dst = 'c:/Users/ELDORBEK ABDUALIMOV/Desktop/ERPPos/frontend/src/pages/admin/PosReturn.jsx'
shutil.copyfile(src, dst)

with open(dst, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Component name
text = text.replace('export default function PosDesktop', 'export default function PosReturn')

# 2. Local storage settings key
text = text.replace('pos_desktop_settings', 'pos_return_settings')

# 3. API endpoints (making sure we don't accidentally replace other api posts if they exist, but there is only api.post('/sales/' or api.post('/sales'))
text = text.replace("api.post('/sales/'", "api.post('/sales/return'")
text = text.replace("api.post('/sales',", "api.post('/sales/return',")

# 4. Text replacements
# The big button
text = text.replace("> To'lash", "> VAZVRAT QILISH")
# The modal header
text = text.replace("To'lovni tasdiqlash", "Vazvratni tasdiqlash")
# The modal save button
text = text.replace("SAQLASH VA CHOP ETISH", "QAYTARISH VA CHOP ETISH")
# Cart empty error
text = text.replace("Savat bo'sh!", "Vazvrat savati bo'sh!")

# 5. UI Color transformations from blue to rose to visually distinguish Returns mode
colors = ['blue-50', 'blue-100', 'blue-200', 'blue-300', 'blue-400', 'blue-500', 'blue-600', 'blue-700', 'blue-800', 'blue-900']
for c in colors:
    rose_c = c.replace('blue', 'rose')
    text = text.replace(f'bg-{c}', f'bg-{rose_c}')
    text = text.replace(f'text-{c}', f'text-{rose_c}')
    text = text.replace(f'border-{c}', f'border-{rose_c}')
    text = text.replace(f'shadow-{c}', f'shadow-{rose_c}')
    text = text.replace(f'ring-{c}', f'ring-{rose_c}')
    
    # for gradients like from-indigo-600 to-blue-700
    text = text.replace(f'to-{c}', f'to-{rose_c}')
    text = text.replace(f'from-{c}', f'from-{rose_c}')

# Fix the gradient start to be red-ish too
text = text.replace('from-indigo-600', 'from-red-600')

with open(dst, 'w', encoding='utf-8') as f:
    f.write(text)

print('Success')
