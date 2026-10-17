// Mijoz profili formasi uchun yordamchilar (CustomerProfileSection bilan birga)
import api from '../../api/axios';

// Hujjatlar (pasport/shartnoma) — faqat vakolatli rollar; backend DOC_VIEW_ROLES / DOC_DELETE_ROLES bilan bir xil
export const DOC_VIEW_ROLES = ['super_admin', 'admin', 'director', 'manager'];
export const DOC_DELETE_ROLES = ['super_admin', 'admin', 'director'];
export const canViewDocs = (role) => DOC_VIEW_ROLES.includes(role);
export const canDeleteDocs = (role) => DOC_DELETE_ROLES.includes(role);

const storedRole = () => {
  try { return JSON.parse(localStorage.getItem('user') || 'null')?.role; } catch { return undefined; }
};

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
export async function uploadPendingFiles(customerId, pending, canDocs = canViewDocs(storedRole())) {
  const errors = [];
  if (pending.photo) {
    const fd = new FormData(); fd.append('file', pending.photo);
    await api.post(`/customers/${customerId}/photo`, fd).catch(e => errors.push(e.response?.data?.detail || pending.photo.name));
  }
  // Hujjat yuklash huquqi bo'lmasa urinmaydi (403 xatosi chiqmasligi uchun)
  for (const doc of canDocs ? (pending.docs || []) : []) {
    const fd = new FormData(); fd.append('file', doc);
    await api.post(`/customers/${customerId}/documents`, fd).catch(e => errors.push(e.response?.data?.detail || doc.name));
  }
  return errors;
}

// ── T1.15: mijoz/buyurtma filiali ──────────────────────────────────────────
// Mijoz filialini o'zgartirish rollari; backend CUSTOMER_BRANCH_ROLES bilan bir xil
export const BRANCH_ASSIGN_ROLES = ['super_admin', 'admin', 'director', 'manager'];
export const canAssignBranch = (role) => BRANCH_ASSIGN_ROLES.includes(role);
// Buyurtmalar ro'yxatida filial filtri — admin/director (backend: hamma filial buyurtmalari)
export const BRANCH_FILTER_ROLES = ['super_admin', 'admin', 'director'];
export const canFilterBranch = (role) => BRANCH_FILTER_ROLES.includes(role);

// Bu vazifa matnlari (uz/ru/en). Umumiy i18n fayllariga ko'chirilgunga qadar shu yerda;
// i18n da bir xil kalit paydo bo'lsa, o'sha ustun turadi.
const BRANCH_I18N = {
  uz: {
    'customer.branch': 'Filial',
    'customer.assignBranch': "Filialni o'zgartirish",
    'customer.noBranch': 'Filialsiz',
    'customer.allBranches': 'Barcha filiallar',
    'customer.branchSaved': 'Filial saqlandi',
    'customer.branchError': "Filialni o'zgartirib bo'lmadi",
    'customer.cashier': 'Kassir',
    'customer.warehouseBranch': 'Ombor / Filial',
    'order.table.branch': 'Filial',
    'order.filterBranch': 'Filial bo\'yicha',
    'order.loadMore': 'Yana yuklash',
    'order.errInvalidTransition': "Bu holatga o'tkazib bo'lmaydi",
  },
  ru: {
    'customer.branch': 'Филиал',
    'customer.assignBranch': 'Изменить филиал',
    'customer.noBranch': 'Без филиала',
    'customer.allBranches': 'Все филиалы',
    'customer.branchSaved': 'Филиал сохранён',
    'customer.branchError': 'Не удалось изменить филиал',
    'customer.cashier': 'Кассир',
    'customer.warehouseBranch': 'Склад / Филиал',
    'order.table.branch': 'Филиал',
    'order.filterBranch': 'По филиалу',
    'order.loadMore': 'Загрузить ещё',
    'order.errInvalidTransition': 'В этот статус перевести нельзя',
  },
  en: {
    'customer.branch': 'Branch',
    'customer.assignBranch': 'Change branch',
    'customer.noBranch': 'No branch',
    'customer.allBranches': 'All branches',
    'customer.branchSaved': 'Branch saved',
    'customer.branchError': 'Could not change the branch',
    'customer.cashier': 'Cashier',
    'customer.warehouseBranch': 'Warehouse / Branch',
    'order.table.branch': 'Branch',
    'order.filterBranch': 'By branch',
    'order.loadMore': 'Load more',
    'order.errInvalidTransition': 'This status change is not allowed',
  },
};

/** t(key) topilmasa (kalit qaytsa) shu yerdagi tarjimadan oladi */
export const tBranch = (t, lang, key) => {
  const v = t(key);
  if (v && v !== key) return v;
  return BRANCH_I18N[lang]?.[key] ?? BRANCH_I18N.uz[key] ?? key;
};
