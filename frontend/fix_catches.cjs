const fs = require('fs');
const path = require('path');

const srcDir = path.join(__dirname, 'src');

function walk(dir, callback) {
  fs.readdirSync(dir).forEach(f => {
    const dirPath = path.join(dir, f);
    const isDirectory = fs.statSync(dirPath).isDirectory();
    isDirectory ? walk(dirPath, callback) : callback(dirPath);
  });
}

let modifiedCount = 0;

walk(srcDir, (filePath) => {
  if (filePath.endsWith('.js') || filePath.endsWith('.jsx')) {
    let content = fs.readFileSync(filePath, 'utf-8');
    
    // Replace .catch(() => {}) and similar constructs
    // Match exactly empty arrow functions inside catch block 
    // Examples: .catch(() => {}), .catch(()=> {}), .catch( () => { } )
    const catchRegex = /\.catch\s*\(\s*\(\s*\)\s*=>\s*\{\s*\}\s*\)/g;
    
    // Also match catches that have an 'e' or 'err' but are completely empty:
    // .catch((err) => {}), .catch(e => {})
    const catchParamRegex = /\.catch\s*\(\s*\(?\s*(err|e|error)\s*\)?\s*=>\s*\{\s*\}\s*\)/g;
    
    const replacement = '.catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") })';
    
    let hasChanges = false;
    
    if (catchRegex.test(content)) {
      content = content.replace(catchRegex, replacement);
      hasChanges = true;
    }
    
    if (catchParamRegex.test(content)) {
      content = content.replace(catchParamRegex, replacement);
      hasChanges = true;
    }

    if (hasChanges) {
      if (!content.includes("import toast")) {
         // Insert import after the first import or at the top
         const importToast = "import toast from 'react-hot-toast';\n";
         const lastImportIndex = content.lastIndexOf("import ");
         if (lastImportIndex !== -1) {
            const endOfLastImport = content.indexOf("\n", lastImportIndex) + 1;
            content = content.slice(0, endOfLastImport) + importToast + content.slice(endOfLastImport);
         } else {
            content = importToast + content;
         }
      }
      fs.writeFileSync(filePath, content, 'utf-8');
      modifiedCount++;
      console.log(`Updated: ${filePath}`);
    }
  }
});

console.log(`Success! Modified ${modifiedCount} files.`);
