import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  queueKey, getPending, setPending, migrateLegacyQueue, getPendingPosCount, flushPosQueue,
} from '../posQueue';

// vitest (node muhiti) da localStorage yo'q — oddiy xotira ko'rinishi
function installStorage() {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, String(v)); },
    removeItem: (k) => { store.delete(k); },
    clear: () => store.clear(),
  };
  return store;
}

describe('posQueue', () => {
  beforeEach(() => {
    installStorage();
    localStorage.setItem('user', JSON.stringify({ id: 5, company_id: 7 }));
  });

  it('kalit korxona bo\'yicha nomlanadi', () => {
    expect(queueKey('pos_pending_sales', 7)).toBe('pos_pending_sales:7');
    expect(queueKey('pos_pending_sales')).toBe('pos_pending_sales:7');
    expect(queueKey('pos_pending_sales', null)).toBe('pos_pending_sales');
  });

  it('eski kalit joriy korxonaga ko\'chiriladi va company_id qo\'shiladi', () => {
    localStorage.setItem('pos_pending_sales', JSON.stringify([{ payload: { a: 1 }, idemKey: 'k1' }]));
    localStorage.setItem('pos_pending_sales:7', JSON.stringify([{ payload: { a: 0 }, idemKey: 'k0' }]));
    migrateLegacyQueue(7);
    expect(localStorage.getItem('pos_pending_sales')).toBeNull();
    const moved = getPending('pos_pending_sales:7');
    expect(moved.map((x) => x.idemKey)).toEqual(['k0', 'k1']);
    expect(moved[1].company_id).toBe(7);
    expect(getPendingPosCount()).toBe(2);
  });

  it('boshqa korxona navbati sanalmaydi va yuborilmaydi', async () => {
    setPending('pos_pending_sales:9', [{ payload: {}, idemKey: 'x', company_id: 9 }]);
    setPending('pos_pending_sales:7', [{ payload: {}, idemKey: 'y', company_id: 7 }]);
    const api = { post: vi.fn().mockResolvedValue({}) };
    const res = await flushPosQueue(api);
    expect(res.sent).toBe(1);
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(getPending('pos_pending_sales:9')).toHaveLength(1);
    expect(getPending('pos_pending_sales:7')).toHaveLength(0);
  });

  it('4xx rad etilganlarga o\'tadi, 5xx navbatda qoladi', async () => {
    setPending('pos_pending_sales:7', [
      { payload: { n: 1 }, idemKey: 'a', company_id: 7 },
      { payload: { n: 2 }, idemKey: 'b', company_id: 7 },
    ]);
    const api = {
      post: vi.fn()
        .mockRejectedValueOnce({ response: { status: 400, data: { detail: 'xato' } } })
        .mockRejectedValueOnce({ response: { status: 503 } }),
    };
    const res = await flushPosQueue(api);
    expect(res.rejected).toBe(1);
    expect(getPending('pos_rejected_sales')).toHaveLength(1);
    expect(getPending('pos_pending_sales:7').map((x) => x.idemKey)).toEqual(['b']);
  });
});
