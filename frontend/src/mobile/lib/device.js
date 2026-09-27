import { Device } from '@capacitor/device';
import { App } from '@capacitor/app';
import { Capacitor } from '@capacitor/core';
import { getItem, setItem } from './storage';

export const APP_VERSION = '1.0.0';

/** Qurilmaning barqaror identifikatori (sessiya shu qurilmaga bog'lanadi) */
export async function getDeviceInfo() {
  let id = await getItem('device_id');
  if (!id) {
    try { id = (await Device.getId()).identifier; } catch { /* brauzer */ }
    if (!id || id.length < 8) id = crypto.randomUUID();
    await setItem('device_id', id);
  }
  let model = null;
  try { const info = await Device.getInfo(); model = [info.manufacturer, info.model].filter(Boolean).join(' '); } catch { /* ignore */ }
  let version = APP_VERSION;
  if (Capacitor.isNativePlatform()) {
    try { version = (await App.getInfo()).version; } catch { /* ignore */ }
  }
  return { device_id: id, platform: Capacitor.getPlatform(), model, app_version: version };
}

/** "1.2.10" > "1.2.9" */
export function versionLess(a, b) {
  const pa = String(a).split('.').map(Number), pb = String(b).split('.').map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const x = pa[i] || 0, y = pb[i] || 0;
    if (x !== y) return x < y;
  }
  return false;
}
