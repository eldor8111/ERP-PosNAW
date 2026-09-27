// Agent ma'lumotlari: onlayn bo'lsa serverdan, bo'lmasa IndexedDB keshidan.
import api from '../lib/api';
import { kvGet, kvSet } from '../offline/db';
import { getItem, removeItem, setItem } from '../lib/storage';

async function cached(key, url) {
  try {
    const { data } = await api.get(url);
    await kvSet(key, data);
    return { data, offline: false };
  } catch {
    const c = await kvGet(key);
    return { data: c?.value ?? null, offline: true, savedAt: c?.saved_at };
  }
}

export const loadCustomers = () => cached('agent_customers', '/mobile/agent/customers');
export const loadCatalog = () => cached('agent_catalog', '/mobile/agent/catalog');
export const loadPlan = () => cached('agent_plan', '/mobile/agent/plan');

/** Backend resolve_price bilan bir xil: maxsus narx > narx turi > sotuv narxi */
export function priceFor(product, customer) {
  const special = customer?.prices?.[String(product.id)];
  if (special != null) return special;
  if (customer?.price_type === 'wholesale') return product.wholesale_price || product.sale_price;
  if (customer?.price_type === 'cost') return product.cost_price || product.sale_price;
  return product.sale_price;
}

// ── Faol tashrif (telefonda saqlanadi, oxirida bitta so'rov bo'lib yuboriladi) ──
export const getActiveVisit = () => getItem('active_visit');
export const setActiveVisit = (v) => setItem('active_visit', v);
export const clearActiveVisit = () => removeItem('active_visit');
