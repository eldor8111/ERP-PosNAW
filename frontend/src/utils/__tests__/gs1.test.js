import { describe, it, expect } from 'vitest';
import { GS, latinize, parseGs1Scan, gtinMatches, gtinVariants, productMatchesGtin, createGsDetector } from '../gs1';

const SIG = 'AbCdEfGhIjKlMnOpQrStUvWxYz0123456789+/AbCdEf';   // 92: 44 belgi
// Lotin matnni rus klaviaturasida terilgandek qiladi (skaner kirill tartibda yozgan holat)
const L = 'qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM/';
const R = 'йцукенгшщзфывапролдячсмитьЙЦУКЕНГШЩЗФЫВАПРОЛДЯЧСМИТЬ.';
const toRu = (s) => [...s].map(ch => (L.includes(ch) ? R[L.indexOf(ch)] : ch)).join('');

describe('gs1: Data Matrix skaneri', () => {
  it('Asl belgisi (dori): 01 21 91 92, GS bilan va GS siz bir xil natija', () => {
    const want = { gtin: '04780069000130', serial: '5k9n2EXwWWGWw', code: `0104780069000130215k9n2EXwWWGWw${GS}91EE10${GS}92${SIG}` };
    expect(parseGs1Scan(`0104780069000130215k9n2EXwWWGWw${GS}91EE10${GS}92${SIG}`)).toMatchObject(want);
    expect(parseGs1Scan(`0104780069000130215k9n2EXwWWGWw91EE1092${SIG}`)).toMatchObject(want);
  });

  it('oziq-ovqat: 01 21 93', () => {
    expect(parseGs1Scan(`010478000000001121abc123${GS}93XyZ1`)).toMatchObject({ gtin: '04780000000011', serial: 'abc123', code: `010478000000001121abc123${GS}93XyZ1` });
    expect(parseGs1Scan('010478000000001121abc12393XyZ1').serial).toBe('abc123');
  });

  it("Yevropa dorisi: 17 muddat, 10 partiya, 21 seriya", () => {
    const r = parseGs1Scan(`01040123456789011727013110LOT7${GS}21SER123`);
    expect(r).toMatchObject({ gtin: '04012345678901', expiry: '270131', lot: 'LOT7', serial: 'SER123' });
  });

  it('qavsli ko\'rinish va ]d2 prefiksi', () => {
    expect(parseGs1Scan('(01)04780000000011(21)ABC123(17)270131(10)L01')).toMatchObject({ gtin: '04780000000011', serial: 'ABC123', lot: 'L01', expiry: '270131' });
    expect(parseGs1Scan(`]d2010478000000001121abc123${GS}93XyZ1`).gtin).toBe('04780000000011');
  });

  it('kirill klaviaturada skanerlangan kod lotinga qaytadi', () => {
    expect(latinize('йцук')).toBe('qwer');
    expect(latinize('12345')).toBe('12345');
    // "abcQ123" va "XyZ1" rus klaviaturasida: ф и с Й ... Ч н Я
    expect(parseGs1Scan('010478000000001121фисЙ12393ЧнЯ1')).toMatchObject({
      gtin: '04780000000011', serial: 'abcQ123', code: `010478000000001121abcQ123${GS}93XyZ1`,
    });
    // Asl belgisi kodi kirillda (GS yo'qolgan): harflar qaytadi, raqamlar o'zgarmaydi
    const r = parseGs1Scan(toRu(`0104780069000130215k9n2EXwWWGWw91EE1092${SIG}`));
    expect(r).toMatchObject({ gtin: '04780069000130', serial: '5k9n2EXwWWGWw', code: `0104780069000130215k9n2EXwWWGWw${GS}91EE10${GS}92${SIG}` });
  });

  it('GS1 Digital Link', () => {
    expect(parseGs1Scan('https://id.gs1.org/01/04780000000011/21/XYZ9')).toMatchObject({ gtin: '04780000000011', serial: 'XYZ9' });
    expect(parseGs1Scan('https://example.uz/check?id=5')).toBeNull();
  });

  it('oddiy shtrix-kod va boshqa matn GS1 emas', () => {
    expect(parseGs1Scan('4780000000011')).toBeNull();
    expect(parseGs1Scan('0104780000000011')).toBeNull();
    expect(parseGs1Scan('hello')).toBeNull();
    expect(parseGs1Scan('')).toBeNull();
  });

  it('GTIN mahsulotga mosligi', () => {
    expect(gtinMatches('04780000000011', '4780000000011')).toBe(true);
    expect(gtinMatches('04780000000011', '4780000000012')).toBe(false);
    expect(gtinVariants('04780000000011')).toEqual(['4780000000011', '04780000000011']);
    expect(productMatchesGtin({ barcode: '111', units: [{ id: 1, barcode: '4780000000011' }] }, '04780000000011')).toBe(true);
    expect(productMatchesGtin({ barcode: '111', extra_barcodes: ['4780000000011'] }, '04780000000011')).toBe(true);
    expect(productMatchesGtin({ barcode: '111' }, '04780000000011')).toBe(false);
  });

  it('skaner GS ni Ctrl+] yoki Alt+0029 bilan yuboradi', () => {
    const d = createGsDetector();
    expect(d({ type: 'keydown', key: ']', ctrlKey: true })).toBe('gs');
    expect(d({ type: 'keydown', key: 'a' })).toBeNull();
    expect(['0', '0', '2', '9'].map(k => d({ type: 'keydown', key: k, altKey: true }))).toEqual(['skip', 'skip', 'skip', 'skip']);
    expect(d({ type: 'keyup', key: 'Alt' })).toBe('gs');
    expect(d({ type: 'keyup', key: 'Alt' })).toBeNull();
  });
});
