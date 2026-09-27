// Capacitor Preferences — ilovada Android SharedPreferences (WebView
// localStorage tozalanib ketishi mumkin), brauzerda localStorage'ga tushadi.
import { Preferences } from '@capacitor/preferences';

const PREFIX = 'ecm_';

export async function getItem(key) {
  const { value } = await Preferences.get({ key: PREFIX + key });
  if (value == null) return null;
  try { return JSON.parse(value); } catch { return value; }
}

export async function setItem(key, value) {
  await Preferences.set({ key: PREFIX + key, value: JSON.stringify(value) });
}

export async function removeItem(key) {
  await Preferences.remove({ key: PREFIX + key });
}
