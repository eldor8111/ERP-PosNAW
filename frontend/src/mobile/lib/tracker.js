// Ish smenasi davomida GPS kuzatuv. Ilovada — fon xizmati (telefon qulflangan
// bo'lsa ham, doimiy bildirishnoma bilan: xodim kuzatuv yoqiqligini ko'rib
// turadi). Brauzerda — faqat sahifa ochiq paytda. Nuqtalar paket bilan
// yuboriladi; internet bo'lmasa telefonda to'planib turadi.
import { Capacitor, registerPlugin } from '@capacitor/core';
import { Device } from '@capacitor/device';
import api from './api';
import { kvGet, kvSet } from '../offline/db';

const BackgroundGeolocation = registerPlugin('BackgroundGeolocation');
const BUFFER_KEY = 'gps_buffer';
const MAX_BUFFER = 3000;
const MIN_INTERVAL_MS = 20000;   // bir nuqtadan keyingisigacha kamida 20 s

let watcherId = null;
let webWatch = null;
let timer = null;
let buffer = [];
let lastAt = 0;
let sending = false;

async function persist() { await kvSet(BUFFER_KEY, buffer.slice(-MAX_BUFFER)); }

function onPoint(lat, lng, accuracy, speed, time) {
  const t = time || Date.now();
  if (t - lastAt < MIN_INTERVAL_MS) return;
  if (accuracy != null && accuracy > 150) return; // juda noaniq nuqta
  lastAt = t;
  buffer.push({ lat, lng, accuracy, speed: speed ?? null, t: new Date(t).toISOString() });
  if (buffer.length > MAX_BUFFER) buffer = buffer.slice(-MAX_BUFFER);
  persist();
  if (buffer.length >= 20) flushPoints();
}

export async function flushPoints() {
  if (sending || buffer.length === 0) return;
  sending = true;
  try {
    let battery = null;
    try { const b = await Device.getBatteryInfo(); battery = b.batteryLevel != null ? Math.round(b.batteryLevel * 100) : null; } catch { /* ignore */ }
    const batch = buffer.slice(0, 500);
    await api.post('/mobile/locations', { points: batch, battery }, { timeout: 15000 });
    buffer = buffer.slice(batch.length);
    await persist();
  } catch { /* oflayn — keyingi safar */ }
  finally { sending = false; }
}

export async function startTracking({ title, message }) {
  if (watcherId || webWatch) return;
  buffer = (await kvGet(BUFFER_KEY))?.value || [];
  if (Capacitor.isNativePlatform()) {
    watcherId = await BackgroundGeolocation.addWatcher(
      { backgroundTitle: title, backgroundMessage: message, requestPermissions: true, stale: false, distanceFilter: 25 },
      (loc, err) => {
        if (err || !loc) return;
        onPoint(loc.latitude, loc.longitude, loc.accuracy, loc.speed, loc.time);
      },
    );
  } else if (navigator.geolocation) {
    webWatch = navigator.geolocation.watchPosition(
      (p) => onPoint(p.coords.latitude, p.coords.longitude, p.coords.accuracy, p.coords.speed, p.timestamp),
      () => {},
      { enableHighAccuracy: true, maximumAge: 15000 },
    );
  }
  timer = setInterval(flushPoints, 60000);
}

export async function stopTracking() {
  if (watcherId) { try { await BackgroundGeolocation.removeWatcher({ id: watcherId }); } catch { /* ignore */ } }
  if (webWatch != null) navigator.geolocation.clearWatch(webWatch);
  watcherId = null; webWatch = null;
  clearInterval(timer); timer = null;
  await flushPoints();
}
