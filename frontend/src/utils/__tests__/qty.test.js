import { describe, it, expect } from 'vitest';
import { fmtQty } from '../qty';

const loc = (n) => n.toLocaleString('uz-UZ', { maximumFractionDigits: 3 });

describe('fmtQty', () => {
  it('server Decimal satri ortiqcha nollarsiz', () => {
    expect(fmtQty('53.000')).toBe('53');
    expect(fmtQty('0.000')).toBe('0');
    expect(fmtQty('2.500')).toBe(loc(2.5));
    expect(fmtQty('1200.000')).toBe(loc(1200));
    expect(fmtQty('-3.000')).toBe(loc(-3));
  });

  it('son o\'zgarmaydi, kasr 3 xonagacha', () => {
    expect(fmtQty(53)).toBe('53');
    expect(fmtQty(0.1234)).toBe(loc(0.123));
  });

  it('bo\'sh qiymat 0, son bo\'lmagan matn o\'zi', () => {
    expect(fmtQty(null)).toBe('0');
    expect(fmtQty(undefined)).toBe('0');
    expect(fmtQty('')).toBe('0');
    expect(fmtQty('abc')).toBe('abc');
  });
});
