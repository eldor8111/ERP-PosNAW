const fs = require('fs');

function sanitizeKey(str) {
    let key = str.toLowerCase().replace(/[^a-z0-9_]/g, '');
    if (!key) key = 'symbol' + Buffer.from(str).toString('hex').substring(0, 4);
    if (key.length > 25) key = key.substring(0, 25);
    return 'auto.' + key;
}

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
let globalNewDict = {};
let filesUpdated = 0;

files.forEach(targetFile => {
    let original = fs.readFileSync(targetFile, 'utf8');
    let content = original;
    
    // 1. Text nodes > Text <
    const matches = [...content.matchAll(/>([^<{}]+)</g)];
    matches.forEach(m => {
        const text = m[1].replace(/^\s+|\s+$/g, '');
        // must have a letter, min length 2, no existing t(
        if (text.length > 1 && /[A-Za-zА-Яа-я]/.test(text) && !text.includes('t(') && !text.startsWith('//')) {
            let key = sanitizeKey(text);
            globalNewDict[key] = text;
            let exactToken = '>' + m[1] + '<';
            let replaceToken = '>' + m[1].replace(text, "{t('" + key + "')}") + '<';
            content = content.split(exactToken).join(replaceToken);
        }
    });

    // 2. Placeholders placeholder="Nimadir"
    const pMatches = [...content.matchAll(/placeholder=(['"])(.*?)\1/g)];
    pMatches.forEach(m => {
        const text = m[2];
        if (text.length > 1 && /[A-Za-zА-Яа-я]/.test(text)) {
            let key = sanitizeKey(text);
            globalNewDict[key] = text;
            let exactToken = 'placeholder=' + m[1] + m[2] + m[1];
            let replaceToken = "placeholder={t('" + key + "')}";
            content = content.split(exactToken).join(replaceToken);
        }
    });

    // 3. title="Nimadir"
    const tMatches = [...content.matchAll(/\stitle=(['"])(.*?)\1/g)];
    tMatches.forEach(m => {
        const text = m[2];
        if (text.length > 1 && /[A-Za-zА-Яа-я]/.test(text)) {
            let key = sanitizeKey(text);
            globalNewDict[key] = text;
            let exactToken = ' title=' + m[1] + m[2] + m[1];
            let replaceToken = " title={t('" + key + "')}";
            content = content.split(exactToken).join(replaceToken);
        }
    });

    if (content !== original) {
        fs.writeFileSync(targetFile, content, 'utf8');
        filesUpdated++;
    }
});

// Write to uz.js
const uzFile = 'c:/ERPPos_extracted/ERPPos/frontend/src/i18n/uz.js';
let uzContent = fs.readFileSync(uzFile, 'utf8');
let appendStr = '\n  // === AUTO TRANSLATIONS ===\n';
for (let key in globalNewDict) {
    let val = globalNewDict[key].replace(/'/g, "\\'");
    appendStr += "  '" + key + "': '" + val + "',\n";
}
uzContent = uzContent.replace(/};\s*$/, appendStr + '};\n');
fs.writeFileSync(uzFile, uzContent, 'utf8');

console.log('Updated ' + filesUpdated + ' JSX files.');
console.log('Added ' + Object.keys(globalNewDict).length + ' keys to uz.js.');
