import { useCallback, useEffect, useState } from 'react';
import { AuthContext } from './authContext';
import api, { clearTokens, loadTokens, onSessionExpired, saveTokens } from './api';
import { getDeviceInfo, versionLess } from './device';
import { getItem, removeItem, setItem } from './storage';
import { wipeAll } from '../offline/db';

export function MobileAuthProvider({ children }) {
  // loading | guest | ready | update_required
  const [status, setStatus] = useState('loading');
  const [user, setUser] = useState(null);

  const applyProfile = useCallback(async (p) => {
    setUser(p);
    await setItem('profile', p);
  }, []);

  const refreshProfile = useCallback(async () => {
    const { data } = await api.get('/mobile/me');
    await applyProfile(data);
    return data;
  }, [applyProfile]);

  useEffect(() => {
    const off = onSessionExpired(async () => {
      await removeItem('profile');
      setUser(null);
      setStatus('guest');
    });
    (async () => {
      const device = await getDeviceInfo();
      try {
        const { data } = await api.get('/mobile/version', { timeout: 8000 });
        if (versionLess(device.app_version, data.min_version)) { setStatus('update_required'); return; }
      } catch { /* oflayn — tekshiruvni o'tkazib yuboramiz */ }

      const tokens = await loadTokens();
      if (!tokens) { setStatus('guest'); return; }
      const cached = await getItem('profile');
      if (cached) { setUser(cached); setStatus('ready'); }
      try {
        await refreshProfile();
        setStatus('ready');
      } catch (e) {
        if (!cached) setStatus(e.response?.status === 401 ? 'guest' : 'ready');
      }
    })();
    return off;
  }, [refreshProfile]);

  const login = useCallback(async (phone, password) => {
    const device = await getDeviceInfo();
    const { data } = await api.post('/mobile/auth/login', { phone, password, ...device });
    // Boshqa xodim shu telefonda ishlagan bo'lsa — uning kesh/navbati qolmasin
    const prev = await getItem('profile');
    if (prev && prev.id !== data.user.id) await wipeAll();
    await saveTokens({ access_token: data.access_token, refresh_token: data.refresh_token });
    await applyProfile(data.user);
    setStatus('ready');
  }, [applyProfile]);

  const logout = useCallback(async () => {
    try { await api.post('/mobile/auth/logout', null, { timeout: 5000 }); } catch { /* oflayn */ }
    await clearTokens();
    await removeItem('profile');
    await wipeAll();
    setUser(null);
    setStatus('guest');
  }, []);

  return (
    <AuthContext.Provider value={{ status, user, login, logout, refreshProfile, setUser: applyProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

