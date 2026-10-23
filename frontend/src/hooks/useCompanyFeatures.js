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
      // D1.1b: dorixona maydonlari doim mavjud (eski server javobida bo'lmasa — o'chiq modul)
      .then(r => { cache = { pharmacy: false, pharmacy_settings: {}, ...r.data }; return cache; })
      .catch(() => { cache = { manufacturing: false, distribution: false, require_shift: false, pharmacy: false, pharmacy_settings: {} }; return cache; })
      .finally(() => { inflight = null; window.dispatchEvent(new Event(EVENT)); });
  }
  return inflight;
}

export function refreshCompanyFeatures() {
  cache = null;
  return load();
}

/** null — hali yuklanmoqda; keyin { manufacturing, distribution, marketplace_agents, require_shift, pharmacy, pharmacy_settings } */
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
