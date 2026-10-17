import { useLang } from '../context/LangContext';
import { useBranch } from '../context/BranchContext';
import { useReportScope } from '../hooks/useReportScope';

// T2.5: hisobot va moliya sahifalari uchun filial selektori.
//  - "Barcha filiallar" (value='') + filiallar; yopilgan filial nomiga "(yopilgan)" qo'shiladi;
//  - allowUnassigned: "Filialsiz" (value='-1') — faqat cheklanmagan foydalanuvchiga (canSelectAll).
//  - T2.1: o'z filiali bilan cheklangan foydalanuvchi (GET /reports/scope) uchun selektor qulflanadi:
//    "Barcha filiallar" yo'q, faqat o'z filiali ko'rsatiladi (backend baribir majburlaydi).
// `branches` — GET /branches (yopilganlarini ham olish uchun ?include_inactive=true).
export const UNASSIGNED_VALUE = '-1';

export default function BranchSelect({
  value, onChange, branches = [], allowUnassigned = false, allLabel, className = '', disabled = false,
}) {
  const { t } = useLang();
  const { canSelectAll } = useBranch();
  const scope = useReportScope();
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };
  if (scope.restricted && scope.branchId) {
    const own = String(scope.branchId);
    const mine = branches.filter(b => scope.allowedBranchIds ? scope.allowedBranchIds.includes(b.id) : String(b.id) === own);
    const list = mine.length ? mine : branches.filter(b => String(b.id) === own);
    const cur = list.some(b => String(b.id) === String(value)) ? String(value) : own;
    return (
      <select
        value={cur}
        disabled={disabled || list.length <= 1}
        onChange={e => onChange(e.target.value)}
        title={tf('reports.scopeRestricted', "Siz faqat o'z filialingiz hisobotini ko'rasiz")}
        className={className || 'px-3 py-2 border border-slate-200 rounded-xl text-sm bg-slate-50 text-slate-600 cursor-not-allowed'}
      >
        {list.length ? list.map(b => (
          <option key={b.id} value={String(b.id)}>{b.name}</option>
        )) : <option value={own}>#{own}</option>}
      </select>
    );
  }
  return (
    <select
      value={value ?? ''}
      disabled={disabled}
      onChange={e => onChange(e.target.value)}
      className={className || 'px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white'}
    >
      <option value="">{allLabel || `🏢 ${t('common.allBranches')}`}</option>
      {branches.map(b => (
        <option key={b.id} value={String(b.id)}>
          {b.is_active === false ? `${b.name} ${tf('reports.closedSuffix', '(yopilgan)')}` : b.name}
        </option>
      ))}
      {allowUnassigned && canSelectAll && (
        <option value={UNASSIGNED_VALUE}>{tf('reports.unassignedBranch', 'Filialsiz')}</option>
      )}
    </select>
  );
}
