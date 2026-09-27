// Ulgurji sotuv yetkazmasi — forma holati <-> API payload

export const EMPTY_DELIVERY = {
  enabled: false, existing: false, status: null,
  address: '', lat: null, lng: null, contact_phone: '', delivery_fee: '', planned_date: '', note: '',
};

/** GET /sales/{id} javobidagi `delivery` dan forma holati */
export const deliveryFromSale = (d) => {
  if (!d) return EMPTY_DELIVERY;
  return {
    enabled: d.status !== 'cancelled',
    existing: true,
    status: d.status,
    address: d.address || '',
    lat: d.lat ?? null,
    lng: d.lng ?? null,
    contact_phone: d.contact_phone || '',
    delivery_fee: d.delivery_fee ? String(d.delivery_fee) : '',
    planned_date: d.planned_date || '',
    note: d.note || '',
  };
};

/** Sotuv payload'i uchun: o'chirilgan va avval bo'lmagan bo'lsa — undefined */
export const deliveryPayload = (v) => {
  if (!v.enabled) return v.existing ? { enabled: false } : undefined;
  return {
    enabled: true,
    address: v.address?.trim() || null,
    lat: v.lat ?? null,
    lng: v.lng ?? null,
    contact_phone: v.contact_phone?.trim() || null,
    delivery_fee: Number(v.delivery_fee) || 0,
    planned_date: v.planned_date || null,
    note: v.note?.trim() || null,
  };
};
