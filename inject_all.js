const fs = require('fs');
const path = require('path');

function walk(dir) {
    let results = [];
    const list = fs.readdirSync(dir);
    list.forEach(file => {
        file = dir + '/' + file;
        const stat = fs.statSync(file);
        if (stat && stat.isDirectory()) { 
            if (!file.includes('node_modules') && !file.includes('i18n')) results = results.concat(walk(file));
        } else { 
            if (file.endsWith('.jsx')) results.push(file);
        }
    });
    return results;
}

const files = walk('c:/ERPPos_extracted/ERPPos/frontend/src/pages');
files.forEach(p => {
    let content = fs.readFileSync(p, 'utf8');

    if (content.includes('t(') && !content.includes('useLang')) {
        let importPath = p.includes('/admin/') ? '../../context/LangContext' : '../context/LangContext';
        
        const importMatch = content.match(/import .*?;?[\r\n]+/);
        if (importMatch) {
            content = content.slice(0, importMatch.index + importMatch[0].length) + 
              "import { useLang } from '" + importPath + "';\n" + 
              content.slice(importMatch.index + importMatch[0].length);
        }
    }

    content = content.replace(/(function\s+[A-Z][A-Za-z0-9_]*\s*\(([^)]*)\)\s*\{)/g, (match, p1, p2) => {
        if (/\bt\b/.test(p2)) return match;
        return match + '\n  const { t } = useLang();';
    });
    
    // For const Component = () => { cases (Arrow functions exported)
    content = content.replace(/(const\s+[A-Z][A-Za-z0-9_]*\s*=\s*\(([^)]*)\)\s*=>\s*\{)/g, (match, p1, p2) => {
        if (/\bt\b/.test(p2)) return match;
        return match + '\n  const { t } = useLang();';
    });

    content = content.replace(/(\n\s*const\s*\{\s*t\s*\}\s*=\s*useLang\(\);\s*){2,}/g, '\n  const { t } = useLang();\n');

    fs.writeFileSync(p, content, 'utf8');
});
console.log('Injected context into ' + files.length + ' files');
