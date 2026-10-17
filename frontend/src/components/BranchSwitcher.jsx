// T1.1: Header'dagi joriy filial ko'rsatkichi / almashtirgich.
// - admin/director va filialsiz manager/accountant: select ("Barcha filiallar" + ro'yxat)
// - biriktirilgan xodim: faqat filial nomi
// - filial biriktirilmagan (2+ filialli korxona): sariq belgi
import { useLang } from '../context/LangContext';
import { useBranch } from '../context/BranchContext';

const BranchIcon = ({ className }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
  </svg>
);

export default function BranchSwitcher() {
  const { t } = useLang();
  const { branches, currentBranchId, canSwitch, canSelectAll, needsAssignment, setBranch, loaded } = useBranch();

  if (!loaded) return null;

  if (needsAssignment) {
    return (
      <div
        title={t('branch.switcher.unassignedHint')}
        className="flex items-center gap-1.5 px-2 md:px-3 py-1 xl:py-1.5 bg-amber-50 border border-amber-200 rounded-full"
      >
        <BranchIcon className="w-4 h-4 text-amber-500" />
        <span className="text-[10px] xl:text-[12px] font-bold text-amber-700 whitespace-nowrap">{t('branch.switcher.unassigned')}</span>
      </div>
    );
  }

  if (!canSwitch) {
    const current = branches.find(b => b.id === currentBranchId);
    if (!current) return null;
    return (
      <div
        title={t('branch.switcher.title')}
        className="flex items-center gap-1.5 px-2 md:px-3 py-1 xl:py-1.5 bg-slate-50 border border-slate-200 rounded-full"
      >
        <BranchIcon className="w-4 h-4 text-slate-500" />
        <span className="text-[10px] xl:text-[12px] font-bold text-slate-600 max-w-[110px] sm:max-w-[160px] truncate">{current.name}</span>
      </div>
    );
  }

  if (branches.length === 0) return null;

  return (
    <div
      title={t('branch.switcher.title')}
      className="flex items-center gap-1.5 px-2 md:px-3 py-1 xl:py-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-full transition-all duration-150"
    >
      <BranchIcon className="w-4 h-4 text-slate-500" />
      <select
        value={currentBranchId ?? ''}
        onChange={e => setBranch(e.target.value || null)}
        className="bg-transparent text-[10px] xl:text-[12px] font-bold text-slate-600 focus:outline-none cursor-pointer max-w-[120px] sm:max-w-[180px]"
      >
        {canSelectAll && <option value="">{t('branch.switcher.all')}</option>}
        {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
      </select>
    </div>
  );
}
