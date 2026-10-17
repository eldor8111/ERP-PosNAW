import { describe, it, expect } from 'vitest';
import { pluCode, parseScaleBarcode, findScaleProduct, SCALE_UNITS } from '../scale';
import { buildShtrixM, buildTma, buildRongta } from '../scaleExport';

describe('scale utils (T3.12)', () => {
  it('SCALE_UNITS kg va g', () => {
    expect(SCALE_UNITS).toEqual(['kg', 'g']);
  });

  it('pluCode: eski qoida va plu_code', () => {
    expect(pluCode({ sku: 'KG-0123' })).toBe('00123');
    expect(pluCode({ sku: 'KG-0123', plu_code: 7 })).toBe('00007');
    expect(pluCode({ sku: 'ABC', id: 42 })).toBe('00042');
  });

  it('parseScaleBarcode', () => {
    expect(parseScaleBarcode('2100123012345')).toEqual({ plu: 123, weightKg: 1.234 });
    expect(parseScaleBarcode('2000123012345').plu).toBe(123);
    expect(parseScaleBarcode('2200123012345').plu).toBe(123);
    expect(parseScaleBarcode('2300123012345')).toBeNull();
    expect(parseScaleBarcode('21001230123')).toBeNull();
  });

  it('findScaleProduct: plu_code bo\'yicha va eski SKU qoidasi', () => {
    const products = [{ id: 1, sku: 'KG-0123', plu_code: 123 }, { id: 2, sku: 'X-0456' }];
    expect(findScaleProduct(products, 123).id).toBe(1);
    expect(findScaleProduct(products, 456).id).toBe(2);
    expect(findScaleProduct(products, 999)).toBeNull();
  });

  it('uchala eksportda PLU bir xil', () => {
    const items = [{ id: 1, name: 'Olma', sku: 'SKU-A1B2C3', plu_code: 77, sale_price: 12000, unit: 'kg' }];
    expect(buildShtrixM(items).startsWith('77;Olma;')).toBe(true);
    expect(buildRongta(items).startsWith('77;OLMA;')).toBe(true);
    const tma = buildTma(items).split('\r\n').find(l => l.startsWith('PLU\t'));
    const cols = tma.split('\t');
    expect(cols[1]).toBe('77');
    expect(cols[14]).toBe('77');
  });

  it('120 ta mahsulot — 120 qator', () => {
    const items = Array.from({ length: 120 }, (_, i) => ({ id: i + 1, name: 'M' + i, sku: 'S' + i, plu_code: i + 1, sale_price: 1, unit: 'kg' }));
    expect(buildShtrixM(items).split('\r\n').filter(Boolean)).toHaveLength(120);
    expect(buildRongta(items).split('\r\n')).toHaveLength(120);
  });
});
