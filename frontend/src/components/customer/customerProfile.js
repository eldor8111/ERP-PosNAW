// Mijoz profili formasi uchun yordamchilar (CustomerProfileSection bilan birga)
import api from '../../api/axios';

export const emptyProfile = () => ({
  region: '', district: '', address: '', lat: null, lng: null, location_source: null,
  extra_phones: [], agent_id: '', work_days: [], visit_radius_m: '', discount_percent: '',
});

export const profileFromCustomer = (c) => ({
  region: c.region || '', district: c.district || '', address: c.address || '',
  lat: c.lat ?? null, lng: c.lng ?? null, location_source: c.location_source || null,
  extra_phones: c.extra_phones || [], agent_id: c.agent_id ? String(c.agent_id) : '',
  work_days: c.work_days || [], visit_radius_m: c.visit_radius_m ?? '',
  discount_percent: c.discount_percent != null && Number(c.discount_percent) !== 0 ? String(Number(c.discount_percent)) : '',
});

export const profilePayload = (f) => ({
  region: f.region || null,
  district: f.district || null,
  address: f.address || null,
  lat: f.lat ?? null,
  lng: f.lng ?? null,
  location_source: f.lat != null ? (f.location_source || 'map') : null,
  extra_phones: (f.extra_phones || []).map(p => p.trim()).filter(Boolean),
  agent_id: f.agent_id ? Number(f.agent_id) : null,
  work_days: f.work_days || [],
  visit_radius_m: f.visit_radius_m === '' || f.visit_radius_m == null ? null : Number(f.visit_radius_m),
  discount_percent: f.discount_percent === '' ? 0 : Number(f.discount_percent),
});

/** Yangi mijozga tanlangan rasm/hujjatlarni saqlangandan keyin yuklaydi */
export async function uploadPendingFiles(customerId, pending) {
  const errors = [];
  if (pending.photo) {
    const fd = new FormData(); fd.append('file', pending.photo);
    await api.post(`/customers/${customerId}/photo`, fd).catch(e => errors.push(e.response?.data?.detail || pending.photo.name));
  }
  for (const doc of pending.docs || []) {
    const fd = new FormData(); fd.append('file', doc);
    await api.post(`/customers/${customerId}/documents`, fd).catch(e => errors.push(e.response?.data?.detail || doc.name));
  }
  return errors;
}
