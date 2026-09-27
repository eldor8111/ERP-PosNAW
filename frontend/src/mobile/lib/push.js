// Push-xabarlar (FCM). Firebase sozlanmagan build'da (google-services.json
// yo'q) PushNotifications.register() Android ilovani yiqitadi — shuning
// uchun faqat VITE_PUSH_ENABLED=true bo'lganda yoqiladi.
import { Capacitor } from '@capacitor/core';
import { PushNotifications } from '@capacitor/push-notifications';
import api from './api';

let started = false;

export async function initPush() {
  if (started || import.meta.env.VITE_PUSH_ENABLED !== 'true' || !Capacitor.isNativePlatform()) return;
  started = true;
  try {
    const perm = await PushNotifications.requestPermissions();
    if (perm.receive !== 'granted') return;
    await PushNotifications.addListener('registration', (t) => {
      api.put('/mobile/device/push-token', { fcm_token: t.value }).catch(() => {});
    });
    await PushNotifications.register();
  } catch { /* push ixtiyoriy — ilova ishlashiga ta'sir qilmaydi */ }
}
