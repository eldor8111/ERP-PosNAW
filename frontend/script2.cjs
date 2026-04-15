const fs = require('fs');
const path = require('path');

const files = [
  'd:/ERPECode/ERP-PosNAW/frontend/src/api/axios.js',
  'd:/ERPECode/ERP-PosNAW/frontend/src/pages/admin/PosKassa.jsx',
  'd:/ERPECode/ERP-PosNAW/frontend/src/pages/admin/UlgurjiSotuv.jsx'
];

for (const f of files) {
  let content = fs.readFileSync(f, 'utf8');
  content = content.replace("import toast from 'react-hot-toast';\n", "");
  fs.writeFileSync(f, content, 'utf8');
  console.log('Fixed', f);
}
