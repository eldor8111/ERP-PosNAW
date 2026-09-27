import { Link } from 'react-router-dom';
import { Lock } from 'lucide-react';
import { useLang } from '../context/LangContext';
import useCompanyFeatures from '../hooks/useCompanyFeatures';

/** Modul o'chiq bo'lsa sahifa o'rniga yoqish yo'lini ko'rsatadi */
export default function FeatureGate({ feature, children }) {
  const { t } = useLang();
  const features = useCompanyFeatures();
  if (features === null) {
    return <div className="flex justify-center py-24"><div className="w-8 h-8 border-4 border-brand border-t-transparent rounded-full animate-spin" /></div>;
  }
  if (features[feature]) return children;
  return (
    <div className="max-w-md mx-auto mt-20 bg-surface border border-line rounded-2xl p-8 text-center shadow-sm">
      <div className="w-12 h-12 mx-auto rounded-2xl bg-surface-sunken flex items-center justify-center text-ink-300">
        <Lock className="size-6" />
      </div>
      <h2 className="mt-4 text-base font-bold text-ink-900">{t(`features.${feature}.title`)}</h2>
      <p className="mt-1.5 text-sm text-ink-500">{t('features.disabledHint')}</p>
      <Link to="/admin/settings" className="inline-block mt-5 px-5 py-2.5 bg-brand hover:bg-brand-deep text-white text-sm font-semibold rounded-xl">
        {t('features.openSettings')}
      </Link>
    </div>
  );
}
