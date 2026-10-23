import { lazy, Suspense, useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useLang } from '../../context/LangContext';
import { useBranch } from '../../context/BranchContext';

// D4.6: Dorixona sahifasi — hisobotlar va partiyalar markazi. D4.1-D4.5 panellarini tablarga ulaydi.
// Faol tab URL hash'ida eslab qolinadi (#expiry, #batches, ...). Marshrut (/admin/pharmacy) App.jsx'da
// FeatureGate feature="pharmacy" bilan o'ralgan — modul o'chiq korxonada bu sahifa ochilmaydi.
const AnalyticsPanel = lazy(() => import('./pharmacy/AnalyticsPanel'));
const ExpiryReport   = lazy(() => import('./pharmacy/ExpiryReport'));
const BatchesPanel   = lazy(() => import('./pharmacy/BatchesPanel'));
const RecallPanel    = lazy(() => import('./pharmacy/RecallPanel'));
const DefekturaPanel = lazy(() => import('./pharmacy/DefekturaPanel'));
const JournalsPanel  = lazy(() => import('./pharmacy/JournalsPanel'));

const TABS = [
  { key: 'analytics', label: 'pharmacyHub.tabAnalytics', fb: "Ko'rsatkichlar" },
  { key: 'expiry',    label: 'pharmacyHub.tabExpiry',    fb: 'Muddatlar' },
  { key: 'batches',   label: 'pharmacyHub.tabBatches',   fb: 'Partiyalar' },
  { key: 'recall',    label: 'pharmacyHub.tabRecall',    fb: 'Qaytarib olish' },
  { key: 'defektura', label: 'pharmacyHub.tabDefektura', fb: 'Defektura' },
  { key: 'journals',  label: 'pharmacyHub.tabJournals',  fb: 'Jurnallar' },
];
const TAB_KEYS = TABS.map(x => x.key);

function TabLoader() {
  return (
    <div className="flex items-center justify-center h-48">
      <div className="w-8 h-8 border-4 border-blue-100 border-t-blue-600 rounded-full animate-spin" />
    </div>
  );
}

export default function PharmacyHub() {
  const { t } = useLang();
  // t(key) kalit topilmasa o'zini qaytaradi — shunda o'zbekcha zaxira matn chiqadi
  const tf = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };
  const location = useLocation();
  const navigate = useNavigate();
  const { currentBranchId } = useBranch();
  const branchId = currentBranchId ? String(currentBranchId) : '';

  const fromHash = useCallback(() => {
    const h = (location.hash || '').replace('#', '');
    return TAB_KEYS.includes(h) ? h : 'analytics';
  }, [location.hash]);
  const [tab, setTab] = useState(fromHash);
  useEffect(() => { setTab(fromHash()); }, [fromHash]);

  const selectTab = (key) => {
    setTab(key);
    navigate({ pathname: location.pathname, search: location.search, hash: `#${key}` }, { replace: true });
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-800">{tf('pharmacyHub.title', 'Dorixona')}</h1>
        <p className="text-sm text-slate-500">{tf('pharmacyHub.desc', "Hisobotlar, partiyalar, qaytarib olish, defektura va jurnallar markazi.")}</p>
      </div>

      <div className="flex gap-1 overflow-x-auto border-b border-slate-200" role="tablist">
        {TABS.map(x => (
          <button
            key={x.key}
            type="button"
            role="tab"
            aria-selected={tab === x.key}
            onClick={() => selectTab(x.key)}
            className={`px-4 py-2 text-sm font-semibold whitespace-nowrap border-b-2 -mb-px transition-colors ${
              tab === x.key ? 'border-blue-600 text-blue-700' : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            {tf(x.label, x.fb)}
          </button>
        ))}
      </div>

      <Suspense fallback={<TabLoader />}>
        {tab === 'analytics' && <AnalyticsPanel branchId={branchId} />}
        {tab === 'expiry' && <ExpiryReport />}
        {tab === 'batches' && <BatchesPanel />}
        {tab === 'recall' && <RecallPanel />}
        {tab === 'defektura' && <DefekturaPanel branchId={branchId} />}
        {tab === 'journals' && <JournalsPanel branchId={branchId} />}
      </Suspense>
    </div>
  );
}
