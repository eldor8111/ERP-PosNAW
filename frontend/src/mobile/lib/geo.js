import { Geolocation } from '@capacitor/geolocation';
import { Capacitor } from '@capacitor/core';

/** Joriy joylashuv yoki null (ruxsat yo'q / GPS o'chiq / vaqt tugadi) */
export async function getPosition({ timeout = 12000 } = {}) {
  try {
    if (Capacitor.isNativePlatform()) {
      const perm = await Geolocation.checkPermissions();
      if (perm.location !== 'granted') {
        const req = await Geolocation.requestPermissions({ permissions: ['location'] });
        if (req.location !== 'granted') return null;
      }
    }
    const p = await Geolocation.getCurrentPosition({ enableHighAccuracy: true, timeout, maximumAge: 30000 });
    return { lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy };
  } catch {
    return null;
  }
}

/** Ikki nuqta orasidagi masofa (metr) */
export function distanceM(a, b) {
  if (!a || !b || a.lat == null || b.lat == null) return null;
  const R = 6371000, rad = (x) => x * Math.PI / 180;
  const dLat = rad(b.lat - a.lat), dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return Math.round(2 * R * Math.asin(Math.sqrt(h)));
}

export const fmtDistance = (m) => m == null ? '' : m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1)} km`;

/** Yandex Navigator/Maps'da yo'l ko'rsatish (ilova bo'lmasa brauzerda ochiladi) */
export const navigateUrl = (lat, lng) => `https://yandex.uz/maps/?rtext=~${lat},${lng}&rtt=auto`;
