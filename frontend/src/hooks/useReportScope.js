import { useState, useEffect } from 'react';
import api from '../api/axios';
import { useAuth } from '../context/AuthContext';
import { ROLE_GROUPS, ROLES } from '../constants/roles';

/**
 * Hisobot filial doirasi (T2.1) — GET /reports/scope bir marta yuklanadi (foydalanuvchi/korxona bo'yicha).
 *
 * `useReportScope()` -> `{ restricted, branchId, canSelectAll, allowedBranchIds, loaded }`
 *  - `restricted` — foydalanuvchi o'z filiali bilan cheklangan (menejer, `reports.all_branches` huquqisiz);
 *    selektor qulflanadi va faqat `branchId` ko'rsatiladi;
 *  - `canSelectAll` — "Butun korxona" tanlash mumkin.
 * Backend baribir majburlaydi (cheklangan menejer boshqa filial uchun 403 oladi) — UI faqat qo'shimcha qatlam.
 * Hisobot rollaridan tashqari foydalanuvchida so'rov yuborilmaydi va cheklov yo'q deb olinadi.
 */
const DEFAULT_SCOPE = { restricted: false, branchId: null, canSelectAll: true, allowedBranchIds: null, loaded: false };

const _promises = new Map(); // `${userId}:${companyId}` -> Promise<scope>

function _normalize(d) {
  return {
    restricted: !!d?.restricted,
    branchId: d?.branch_id ?? null,
    canSelectAll: d?.can_select_all !== false,
    allowedBranchIds: Array.isArray(d?.allowed_branch_ids) ? d.allowed_branch_ids : null,
    loaded: true,
  };
}

function _load(key) {
  if (!_promises.has(key)) {
    const p = api.get('/reports/scope', { _suppressToast: true })
      .then(r => _normalize(r.data))
      .catch(() => {
        _promises.delete(key); // keyingi urinishda qayta so'raladi
        return { ...DEFAULT_SCOPE, loaded: true };
      });
    _promises.set(key, p);
  }
  return _promises.get(key);
}

export function useReportScope() {
  const { user } = useAuth();
  // Faqat hisobot rollari uchun so'raladi (kassir va h.k. uchun so'rov yo'q — 403 konsolda ko'rinmasin)
  const eligible = !!user && (ROLE_GROUPS.REPORTS_ACCESS.includes(user.role) || user.role === ROLES.SUPER_ADMIN);
  const key = eligible ? `${user.id}:${user.company_id ?? ''}` : null;
  const [scope, setScope] = useState(DEFAULT_SCOPE);

  useEffect(() => {
    if (!key) { setScope(DEFAULT_SCOPE); return; }
    let alive = true;
    _load(key).then(s => { if (alive) setScope(s); });
    return () => { alive = false; };
  }, [key]);

  return scope;
}

export default useReportScope;
