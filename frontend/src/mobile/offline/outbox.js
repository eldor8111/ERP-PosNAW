// Oflayn amallar navbati. Har bir amal o'z Idempotency-Key'i bilan
// yuboriladi — tarmoq uzilib qayta yuborilsa ham serverda bir marta yoziladi.
import { Network } from '@capacitor/network';
import { App } from '@capacitor/app';
import api from '../lib/api';
import { outboxAll, outboxDel, outboxPut } from './db';

const EVENT = 'outbox-changed';
let flushing = null;

const notify = async () => {
  const items = await outboxAll();
  window.dispatchEvent(new CustomEvent(EVENT, { detail: items }));
};

/**
 * Amalni navbatga qo'shadi va darhol yuborishga urinadi.
 * label — foydalanuvchiga ko'rinadigan qisqa tavsif ("Buyurtma: Anvar do'kon").
 */
export async function enqueue({ method = 'post', url, body, label }) {
  const item = {
    id: crypto.randomUUID(),
    idem_key: crypto.randomUUID(),
    method, url, body, label,
    created_at: Date.now(),
    attempts: 0,
    state: 'pending',   // pending | failed (server rad etdi)
    error: null,
  };
  await outboxPut(item);
  await notify();
  flush();
  return item;
}

export async function removeItem(id) { await outboxDel(id); await notify(); }

export async function retryItem(id) {
  const items = await outboxAll();
  const it = items.find(x => x.id === id);
  if (it) { await outboxPut({ ...it, state: 'pending', error: null }); await notify(); flush(); }
}

async function sendOne(it) {
  try {
    await api.request({ method: it.method, url: it.url, data: it.body, headers: { 'Idempotency-Key': it.idem_key } });
    await outboxDel(it.id);
    return 'ok';
  } catch (e) {
    const status = e.response?.status;
    if (!status || status >= 500 || status === 408 || status === 429 || status === 401) {
      await outboxPut({ ...it, attempts: it.attempts + 1 });
      return 'retry-later';   // tarmoq/server — keyinroq
    }
    const detail = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : `Xato ${status}`;
    await outboxPut({ ...it, attempts: it.attempts + 1, state: 'failed', error: detail });
    return 'failed';          // server rad etdi — foydalanuvchi ko'rib chiqadi
  }
}

/** Navbatni tartib bilan yuboradi; tarmoq xatosida to'xtaydi */
export function flush() {
  if (flushing) return flushing;
  flushing = (async () => {
    try {
      const status = await Network.getStatus().catch(() => ({ connected: navigator.onLine }));
      if (!status.connected) return;
      for (const it of await outboxAll()) {
        if (it.state !== 'pending') continue;
        const res = await sendOne(it);
        if (res === 'retry-later') break;
      }
    } finally {
      flushing = null;
      await notify();
    }
  })();
  return flushing;
}

export function subscribe(fn) {
  const h = (e) => fn(e.detail);
  window.addEventListener(EVENT, h);
  outboxAll().then(fn);
  return () => window.removeEventListener(EVENT, h);
}

let started = false;
/** Internet qaytganda, ilova ochilganda va har 30 soniyada yuboradi */
export function startAutoFlush() {
  if (started) return;
  started = true;
  Network.addListener('networkStatusChange', (s) => { if (s.connected) flush(); }).catch(() => {});
  App.addListener('resume', () => flush()).catch(() => {});
  window.addEventListener('online', () => flush());
  setInterval(flush, 30000);
  flush();
}
