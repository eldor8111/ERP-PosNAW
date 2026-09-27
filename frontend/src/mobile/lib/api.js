// E-code Mobile API klienti. Veb-paneldagi axios'dan alohida: tokenlar
// Preferences'da, refresh — qurilmaga bog'langan /mobile/auth/refresh.
import axios from 'axios';
import { getItem, setItem, removeItem } from './storage';

export const API_URL = import.meta.env.VITE_MOBILE_API_URL || import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
export const API_ORIGIN = API_URL.replace(/\/api\/?$/, '');

let tokens = null; // { access_token, refresh_token } — xotirada kesh
const listeners = new Set();

export async function loadTokens() {
  tokens = await getItem('tokens');
  return tokens;
}
export async function saveTokens(t) {
  tokens = t;
  await setItem('tokens', t);
}
export async function clearTokens() {
  tokens = null;
  await removeItem('tokens');
}
/** Sessiya tugaganda (qurilma uzilgan, refresh eskirgan) chaqiriladi */
export function onSessionExpired(fn) { listeners.add(fn); return () => listeners.delete(fn); }

const api = axios.create({ baseURL: API_URL, timeout: 20000 });

api.interceptors.request.use((config) => {
  if (tokens?.access_token) config.headers.Authorization = `Bearer ${tokens.access_token}`;
  return config;
});

let refreshing = null;
async function refresh() {
  if (!tokens?.refresh_token) throw new Error('no-refresh');
  if (!refreshing) {
    refreshing = axios.post(`${API_URL}/mobile/auth/refresh`, { refresh_token: tokens.refresh_token }, { timeout: 15000 })
      .then(async (r) => { await saveTokens({ ...tokens, ...r.data }); return r.data.access_token; })
      .finally(() => { refreshing = null; });
  }
  return refreshing;
}

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;
    if (status === 401 && original && !original._retried && !original.url?.includes('/mobile/auth/')) {
      original._retried = true;
      try {
        const access = await refresh();
        original.headers.Authorization = `Bearer ${access}`;
        return api(original);
      } catch (e) {
        // Tarmoq xatosida sessiyani tashlamaymiz — faqat server rad etsa
        if (e?.response?.status === 401 || e?.message === 'no-refresh') {
          await clearTokens();
          listeners.forEach(fn => fn());
        }
      }
    }
    return Promise.reject(error);
  },
);

export const errText = (e, fallback = 'Xatolik') =>
  (typeof e?.response?.data?.detail === 'string' && e.response.data.detail)
  || (!e?.response && 'Internet aloqasi yo\'q')
  || fallback;

export default api;
