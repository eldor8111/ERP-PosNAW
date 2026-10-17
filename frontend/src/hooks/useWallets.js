import { useState, useEffect, useCallback } from 'react';
import api from '../api/axios';
import { useBranch } from '../context/BranchContext';

/**
 * Kassa (hamyon) ro'yxati va standart kassa — ro'yxatdagi BIRINCHI element emas (T1.10).
 *
 * `useWallets({ branchId, purpose })` -> `{ wallets, defaultId, loading, reload }`
 *  - `branchId` berilsa: shu filial va umumiy (filialsiz) kassalar (`usable=true`);
 *    berilmasa: joriy filial (BranchContext), u ham bo'lmasa foydalanuvchiga ko'rinadigan hamma kassa.
 *  - `purpose` — hozircha faqat belgi (masalan 'sale' | 'debt_payment' | 'shift_close'); backend qoidasi bir xil.
 *  - `defaultId`: avval `is_default_for_me`, so'ng aynan shu filial kassasi (bitta bo'lsa),
 *    aks holda '' — foydalanuvchi o'zi tanlaydi.
 */
export function useWallets({ branchId, purpose, enabled = true } = {}) {
  const { currentBranchId, assignedBranchId } = useBranch();
  const effectiveBranch = branchId ?? currentBranchId ?? assignedBranchId ?? null;
  const [wallets, setWallets] = useState([]);
  const [loading, setLoading] = useState(!!enabled);

  const load = useCallback(async () => {
    if (!enabled) { setLoading(false); return; }
    setLoading(true);
    try {
      const params = {};
      if (effectiveBranch) { params.branch_id = effectiveBranch; params.usable = true; }
      const { data } = await api.get('/finance/wallets', { params });
      setWallets(Array.isArray(data) ? data : []);
    } catch {
      setWallets([]);
    } finally {
      setLoading(false);
    }
  }, [enabled, effectiveBranch]);

  useEffect(() => { load(); }, [load, purpose]);

  let defaultId = '';
  const mine = wallets.find(w => w.is_default_for_me);
  if (mine) {
    defaultId = String(mine.id);
  } else if (effectiveBranch) {
    const own = wallets.filter(w => w.branch_id === Number(effectiveBranch));
    if (own.length === 1) defaultId = String(own[0].id);
  }

  return { wallets, defaultId, loading, reload: load };
}

export default useWallets;
