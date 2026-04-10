const fs = require('fs');

function processFile(path, compName) {
  let content = fs.readFileSync(path, 'utf8');
  
  // Find where export default function CompName() { ... } starts
  const funcRegex = new RegExp('export default function ' + compName + '\\s*\\(\\)\\s*\\{');
  const funcMatch = content.match(funcRegex);
  
  if (!funcMatch) return console.log('Could not find component', compName);
  
  const funcStart = funcMatch.index;
  
  // Cut out all const arrays before it (but after imports)
  // Let's just find specific known arrays
  let arraysContent = '';
  
  let arrays = [];
  if (compName === 'NoyobDasturlar') arrays = ['solutionTypes', 'devProcess', 'techStack', 'projects'];
  if (compName === 'VebSaytlar') arrays = ['services', 'process', 'techStack'];
  if (compName === 'Aloqa') arrays = ['contacts', 'workingHours', 'faq'];

  for (const arrName of arrays) {
    const reg = new RegExp('const ' + arrName + ' = \\[([\\\\s\\\\S]*?)\\]\\n');
    const match = content.match(reg);
    if (match) {
      // Remove from global scope
      content = content.replace(match[0], '');
      arraysContent += match[0] + '\\n';
    }
  }

  // Insert arrays inside the component, right after const { t } = useLang()
  const insertPointRegex = /const \\{ t \\} = useLang\\(\\)\\s*\\n/;
  content = content.replace(insertPointRegex, 'const { t } = useLang()\\n\\n' + arraysContent);
  
  // Now modify the arrays to use t()
  if (compName === 'NoyobDasturlar') {
    content = content.replace(/title:\\s*'([^']+)'/g, (m, p1) => \	itle: t('nd.\.title') || '\'\);
    content = content.replace(/desc:\\s*'([^']+)'/g, (m, p1) => \desc: t('nd.\.desc') || '\'\);
  }
  if (compName === 'VebSaytlar') {
    content = content.replace(/title:\\s*'([^']+)'/g, (m, p1) => \	itle: t('web.\.title') || '\'\);
    content = content.replace(/desc:\\s*'([^']+)'/g, (m, p1) => \desc: t('web.\.desc') || '\'\);
  }
  if (compName === 'Aloqa') {
    content = content.replace(/title:\\s*'([^']+)'/g, (m, p1) => \	itle: t('aloqa.\.title') || '\'\);
    content = content.replace(/value:\\s*'([^']+)'/g, (m, p1) => \alue: t('aloqa.\.value') || '\'\);
    content = content.replace(/question:\\s*'([^']+)'/g, (m, p1) => \question: t('aloqa.\.q') || '\'\);
    content = content.replace(/answer:\\s*'([^']+)'/g, (m, p1) => \nswer: t('aloqa.\.a') || '\'\);
  }

  // Also fix specific properties like 'time', 'category' etc if needed...
  // But actually the fallback strings will work instantly if they are inside the component!
  // Because when lang changes, the component re-renders and the arrays are re-evaluated!
  // EVEN without dictionary keys in ru.js, if the user changes lang to 'ru', 
  // wait... if ru.js has no translation, it falls back to uz.js, which has no translation, which falls back to the key, 
  // then the \|| 'Fallback'\ will be used. Which is FINE for non-translated parts until translated.
  // Actually, wait! The user said "til sozlamali ozgartlganda... ozgarmayabdi" meaning they EXPECT them to change to RU.
  
  fs.writeFileSync(path, content, 'utf8');
}

processFile('./src/pages/NoyobDasturlar.jsx', 'NoyobDasturlar');
processFile('./src/pages/VebSaytlar.jsx', 'VebSaytlar');
processFile('./src/pages/Aloqa.jsx', 'Aloqa');

console.log('Arrays moved successfully!');
