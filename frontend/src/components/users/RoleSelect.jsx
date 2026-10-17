import { useLang } from '../../context/LangContext';

// T3.4: xodim formalari uchun umumiy rol tanlash (Users.jsx va Settings/Users.jsx).
//  - "Tizim rollari" (enum) va "Maxsus rollar" (dinamik, roles jadvali) bitta select'da.
//  - Maxsus rol tanlansa "Asosiy rol" select'i chiqadi (default cashier) va `role` + `role_id` ikkalasi yuboriladi.
//  - Hozircha custom_role.permissions backendda qo'llanmaydi — server huquqlari asosiy rol bo'yicha (izoh ko'rsatiladi).
// Props: role, roleId, onChange({ role, role_id }), roles (enum ro'yxati), roleLabels, dynamicRoles, children (qo'shimcha izoh).
// i18n kaliti topilmasa (t() kalitni qaytaradi) — o'zbekcha zaxira matn.
const tfWith = (t) => (key, fallback) => { const s = t(key); return s === key ? fallback : s; };

export const DEFAULT_BASE_ROLE = 'cashier';
// Maxsus rolga asosiy rol sifatida admin/director berilmaydi (to'liq huquq bermaslik uchun)
const NON_BASE_ROLES = ['admin', 'director', 'super_admin'];

const inp = "w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100 disabled:text-slate-500 disabled:cursor-not-allowed";

export default function RoleSelect({
  role, roleId, onChange, roles = [], roleLabels = {}, dynamicRoles = [], children,
}) {
  const { t } = useLang();
  const tf = tfWith(t);
  const isCustom = !!roleId;
  const val = isCustom ? `dyn_${roleId}` : (role || '');

  const handleChange = (e) => {
    const v = e.target.value;
    if (v.startsWith('dyn_')) {
      const keep = role && !NON_BASE_ROLES.includes(role) ? role : DEFAULT_BASE_ROLE;
      onChange({ role: keep, role_id: parseInt(v.slice(4), 10) });
    } else {
      onChange({ role: v, role_id: null });
    }
  };

  // Joriy asosiy rol ro'yxatda bo'lmasa (masalan eski admin) ham ko'rinsin
  const baseOptions = roles.filter(r => !NON_BASE_ROLES.includes(r) || r === role);

  return (
    <div>
      <label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('user.role')}</label>
      <select value={val} onChange={handleChange} className={inp} required>
        <option value="" disabled>{t('user.selectRolePlaceholder')}</option>
        <optgroup label={tf('user.systemRoles', 'Tizim rollari')}>
          {roles.map(r => <option key={r} value={r}>{roleLabels[r] || r}</option>)}
        </optgroup>
        {dynamicRoles.length > 0 && (
          <optgroup label={tf('user.customRoles', 'Maxsus rollar')}>
            {dynamicRoles.map(r => <option key={`dyn_${r.id}`} value={`dyn_${r.id}`}>{r.name}</option>)}
          </optgroup>
        )}
      </select>
      {isCustom && (
        <div className="mt-2">
          <label className="block text-xs font-semibold text-slate-600 mb-1.5">{tf('user.baseRole', 'Asosiy rol')}</label>
          <select value={role || DEFAULT_BASE_ROLE} onChange={e => onChange({ role: e.target.value, role_id: roleId })} className={inp}>
            {baseOptions.map(r => <option key={r} value={r}>{roleLabels[r] || r}</option>)}
          </select>
          <p className="mt-1.5 text-[11px] text-amber-700 bg-amber-50 rounded-lg px-2.5 py-1.5">
            {tf('user.customRoleNote', "Server huquqlari asosiy rol bo'yicha beriladi")}
          </p>
        </div>
      )}
      {children}
    </div>
  );
}
