import { useLang } from '../../context/LangContext';

// T3.4: xodim formalari uchun umumiy filial tanlash (Users.jsx va Settings/Users.jsx).
//  - allowEmpty: "— Filialsiz —" varianti (admin/director kabi filialga bog'lanmagan rollar uchun);
//    aks holda birinchi variant disabled "Filialni tanlang" va select `required`.
//    Berilmasa `role` bo'yicha aniqlanadi (BRANCH_REQUIRED_ROLES dan tashqari rollarga bo'sh variant ruxsat).
//  - required: majburiylikni qo'lda belgilash (masalan, filialsiz eski xodimni tahrirlashda false).
//  - multi: manager/accountant uchun bir nechta filial (checkbox ro'yxat; `values`, `onChangeMany`).
//  - Tanlangan filialda faol ombor yo'q (`warehouses_count === 0`) bo'lsa — amber ogohlantirish.
// i18n kaliti topilmasa (t() kalitni qaytaradi) — o'zbekcha zaxira matn.
const tfWith = (t) => (key, fallback) => { const s = t(key); return s === key ? fallback : s; };

// Backend (users.py `_BRANCH_REQUIRED_ROLES`) bilan bir xil: bu rollar 2+ filialli korxonada filialsiz bo'lmaydi
export const BRANCH_REQUIRED_ROLES = ['cashier', 'warehouse', 'agent', 'courier'];

// Filial nomi; topilmasa yoki nofaol bo'lsa belgilanadi (UI-16)
export function branchLabel(branches, id, tf) {
  const b = branches.find(x => x.id === Number(id));
  if (!b) return tf('user.branchOtherInactive', `#${id} (nofaol/boshqa)`);
  return b.is_active === false ? `${b.name} (${tf('user.branchInactive', 'nofaol')})` : b.name;
}

const inp = "w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100 disabled:text-slate-500 disabled:cursor-not-allowed";

export default function BranchSelect({
  value, onChange, branches = [], role, allowEmpty, required,
  multi = false, values = [], onChangeMany,
}) {
  const { t } = useLang();
  const tf = tfWith(t);
  const active = branches.filter(b => b.is_active !== false);
  const canBeEmpty = allowEmpty !== undefined ? !!allowEmpty : !BRANCH_REQUIRED_ROLES.includes(role);
  const isRequired = required !== undefined ? !!required : !canBeEmpty;

  const noWarehouseWarn = (ids) => {
    const bad = ids.map(id => branches.find(b => b.id === Number(id))).filter(b => b && b.warehouses_count === 0);
    if (!bad.length) return null;
    return (
      <p className="mt-1.5 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5">
        {tf('user.branchNoWarehouse', "Bu filialda faol ombor yo'q — sotuvlar boshqa ombordan yechilishi mumkin")}
        {ids.length > 1 ? `: ${bad.map(b => b.name).join(', ')}` : ''}
      </p>
    );
  };

  if (multi) {
    // Tanlangan, lekin faol bo'lmagan filiallar ham ro'yxatda ko'rinadi (state yo'qolmasin)
    const sel = values.map(Number);
    const extra = sel.filter(id => !active.some(b => b.id === id));
    const toggle = (id) => onChangeMany(sel.includes(id) ? sel.filter(x => x !== id) : [...sel, id]);
    return (
      <div>
        <label className="block text-xs font-semibold text-slate-600 mb-1.5">{t('branch.title')}</label>
        <div className="max-h-40 overflow-y-auto border border-slate-200 rounded-xl p-2 space-y-1">
          {active.map(b => (
            <label key={b.id} className="flex items-center gap-2 text-sm text-slate-700 px-2 py-1 rounded-lg hover:bg-slate-50 cursor-pointer">
              <input type="checkbox" checked={sel.includes(b.id)} onChange={() => toggle(b.id)} />
              {b.name}
            </label>
          ))}
          {extra.map(id => (
            <label key={id} className="flex items-center gap-2 text-sm text-amber-700 px-2 py-1 rounded-lg hover:bg-amber-50 cursor-pointer">
              <input type="checkbox" checked onChange={() => toggle(id)} />
              {branchLabel(branches, id, tf)}
            </label>
          ))}
        </div>
        <p className="text-xs text-slate-400 mt-1">{tf('user.branchesMultiHint', "Bir nechta filialni tanlash mumkin")}</p>
        {noWarehouseWarn(sel)}
      </div>
    );
  }

  const cur = value === '' || value == null ? null : Number(value);
  const extraId = cur !== null && !active.some(b => b.id === cur) ? cur : null;
  return (
    <div>
      <label className="block text-xs font-semibold text-slate-600 mb-1.5">
        {t('branch.title')}{isRequired ? ' *' : ''}
      </label>
      <select
        value={value ?? ''}
        onChange={e => onChange(e.target.value)}
        className={inp}
        required={isRequired}
        title={isRequired ? tf('user.branchRequired', 'Bu rol uchun filial tanlanishi shart') : undefined}
      >
        {canBeEmpty
          ? <option value="">{t('user.noBranch')}</option>
          : <option value="" disabled>{tf('user.selectBranchPlaceholder', 'Filialni tanlang')}</option>}
        {active.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
        {extraId !== null && <option value={extraId}>{branchLabel(branches, extraId, tf)}</option>}
      </select>
      {noWarehouseWarn(cur !== null ? [cur] : [])}
    </div>
  );
}
