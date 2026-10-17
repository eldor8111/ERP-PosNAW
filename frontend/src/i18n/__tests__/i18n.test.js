// T3.5: i18n tekshiruvlari (vitest).
//  - kodda ishlatilgan t('...') kalitlari uz lug'atida bor
//  - en va ru kalitlari uz kalitlarini to'liq qoplaydi
//  - i18n/*.js da takroriy kalit yo'q
//  - mojibake (buzilgan kodlash) yo'q
//  - ko'plik shakllari (Intl.PluralRules)
//
// Yakuniy birlashtirishgacha yangi kalitlar src/i18n/pending/*.json da turadi:
// test ularni lug'atlarga qo'shilgan holatda tekshiradi (birlashtirilgach natija o'zgarmaydi).
import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, dirname, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import translations, { createTranslator } from '../index.js';

const here = dirname(fileURLToPath(import.meta.url));
const i18nDir = join(here, '..');
const srcDir = join(i18nDir, '..');
const LANGS = ['uz', 'ru', 'en'];

// ── pending/*.json ni lug'atlarga qo'shamiz (birlashtirilgandan keyingi holat) ──
const pendingDir = join(i18nDir, 'pending');
const pending = { uz: {}, ru: {}, en: {} };
try {
  for (const f of readdirSync(pendingDir).filter((n) => n.endsWith('.json')).sort()) {
    const data = JSON.parse(readFileSync(join(pendingDir, f), 'utf8'));
    for (const lang of LANGS) Object.assign(pending[lang], data[lang] || {});
  }
} catch { /* pending papkasi bo'lmasa — e'tibor bermaymiz */ }
for (const lang of LANGS) Object.assign(translations[lang], pending[lang]);

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) {
      if (name === 'node_modules' || name === '__tests__') continue;
      walk(p, out);
    } else if (/\.(js|jsx)$/.test(name)) {
      out.push(p);
    }
  }
  return out;
}
const sourceFiles = walk(srcDir);
// (i18n/ papkasining o'z fayllari — lug'atlar va index.js — kalit ishlatilishi sifatida sanalmaydi)
const isDictFile = (p) => {
  const rel = relative(i18nDir, p);
  return !rel.startsWith('..') && !rel.includes(sep);
};

describe('i18n lug\'atlari', () => {
  it('ishlatilgan har bir t(\'...\') kaliti uz lug\'atida bor', () => {
    const rx = /(?<![\w$.])t\(\s*(['"])([A-Za-z0-9_.-]+)\1\s*[,)]/g;
    const missing = {};
    for (const file of sourceFiles) {
      if (isDictFile(file)) continue;
      const src = readFileSync(file, 'utf8');
      for (const m of src.matchAll(rx)) {
        const key = m[2];
        if (!(key in translations.uz)) (missing[key] ||= new Set()).add(relative(srcDir, file));
      }
    }
    const report = Object.entries(missing).map(([k, files]) => `${k}  <- ${[...files].join(', ')}`);
    expect(report).toEqual([]);
  });

  for (const lang of ['en', 'ru']) {
    it(`${lang} kalitlari uz kalitlarining to'liq to'plamini o'z ichiga oladi`, () => {
      const missing = Object.keys(translations.uz).filter((k) => !(k in translations[lang]));
      expect(missing).toEqual([]);
    });
  }

  it('i18n/*.js da takroriy kalit yo\'q', () => {
    const rx = /^\s*(?:'((?:[^'\\]|\\.)+)'|"((?:[^"\\]|\\.)+)"|([A-Za-z_$][\w$]*))\s*:/gm;
    const dupes = [];
    for (const lang of LANGS) {
      const src = readFileSync(join(i18nDir, `${lang}.js`), 'utf8');
      const seen = new Set();
      for (const m of src.matchAll(rx)) {
        const key = m[1] ?? m[2] ?? m[3];
        if (seen.has(key)) dupes.push(`${lang}: ${key}`);
        seen.add(key);
      }
    }
    expect(dupes).toEqual([]);
  });

  it("pending fayllaridagi yangi uz kalitlari ru va en da ham bor", () => {
    // yangi kalit (uz da faqat pending orqali kelgan) en/ru da ham bo'lishi shart
    const fresh = Object.keys(pending.uz);
    const bad = [];
    for (const k of fresh) {
      for (const lang of ['ru', 'en']) if (!(k in pending[lang]) && !(k in translations[lang])) bad.push(`${lang}: ${k}`);
    }
    expect(bad).toEqual([]);
  });
});

describe('mojibake', () => {
  it('manba fayllarda buzilgan kodlash (mojibake) belgilari yo\'q', () => {
    // Namunalar: UTF-8 baytlari cp1251 deb noto'g'ri o'qilganda hosil bo'ladigan belgilar (kod nuqtalari bilan —
    // test fayli o'zi mojibake skaneriga tushmasligi uchun)
    const ch = (...cps) => String.fromCharCode(...cps);
    const rx = new RegExp(`${ch(0x442, 0x410, 0x424)}|${ch(0x442, 0x42c)}[${ch(0x400)}-${ch(0x4ff)}]|${ch(0x432, 0x402)}.`);
    const bad = sourceFiles.filter((f) => rx.test(readFileSync(f, 'utf8'))).map((f) => relative(srcDir, f));
    expect(bad).toEqual([]);
  });
});

describe('ko\'plik shakllari', () => {
  it('ru: 1 склад, 2 склада, 5 складов', () => {
    const t = createTranslator('ru');
    expect(t('branch.warehouseCount', { count: 1 })).toBe('1 склад');
    expect(t('branch.warehouseCount', { count: 2 })).toBe('2 склада');
    expect(t('branch.warehouseCount', { count: 5 })).toBe('5 складов');
    expect(t('branch.warehouseCount', { count: 21 })).toBe('21 склад');
  });

  it('en: 1 warehouse, 2 warehouses', () => {
    const t = createTranslator('en');
    expect(t('branch.warehouseCount', { count: 1 })).toBe('1 warehouse');
    expect(t('branch.warehouseCount', { count: 2 })).toBe('2 warehouses');
  });

  it('uz: ko\'plik qoidasi yo\'q — matn o\'zgarmaydi', () => {
    const t = createTranslator('uz');
    expect(t('branch.warehouseCount', { count: 1 })).toBe('1 ta ombor');
    expect(t('branch.warehouseCount', { count: 7 })).toBe('7 ta ombor');
  });

  it('ko\'plik varianti bo\'lmagan kalit eski xatti-harakatni saqlaydi', () => {
    const t = createTranslator('ru');
    expect(t('branch.confirmDeactivate', { name: 'A', count: 3 })).toBe('Деактивировать филиал "A"?');
    // topilmagan kalit — kalitning o'zi
    expect(t('no.such.key', { count: 1 })).toBe('no.such.key');
  });
});
