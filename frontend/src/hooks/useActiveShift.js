import { useState, useEffect, useCallback } from 'react';
import api from '../api/axios';

export function useActiveShift() {
  const [shift, setShift] = useState(undefined); // undefined=loading, null=yo'q, obj=bor
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/shifts/current', { _silent: true });
      setShift(data || null);
    } catch {
      setShift(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return { shift, loading, reload: load, hasShift: !!shift };
}
