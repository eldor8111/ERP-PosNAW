import { useEffect, useState } from 'react';
import api from '../api/axios';

// Kompaniyada yoqilgan ixtiyoriy modullar (Sozlamalar → Umumiy).
// Bir marta yuklanadi va barcha komponentlar o'rtasida bo'lishiladi;
// sozlama o'zgarsa `refreshCompanyFeatures()` hammasini yangilaydi.
const EVENT = 'company-features-updated';
let cache = null;
let inflight = null;

function load() {
  if (!inflight) {
    inflight = api.get('/companies/me/features', { _silent: true })
      .then(r => { cache = r.data; return cache; })
      .catch(() => { cache = { manufacturing: false, distribution: false }; return cache; })
      .finally(() => { inflight = null; window.dispatchEvent(new Event(EVENT)); });
  }
  return inflight;
}

export function refreshCompanyFeatures() {
  cache = null;
  return load();
}

/** null — hali yuklanmoqda; keyin { manufacturing, distribution } */
export default function useCompanyFeatures() {
  const [features, setFeatures] = useState(cache);
  useEffect(() => {
    const onUpdate = () => setFeatures(cache);
    window.addEventListener(EVENT, onUpdate);
    if (!cache) load();
    return () => window.removeEventListener(EVENT, onUpdate);
  }, []);
  return features;
}
