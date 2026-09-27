import { openDB } from 'idb';

// kv     — oflayn kesh (katalog, mijozlar, kunlik reja, marshrut...)
// outbox — internet yo'qligida yaratilgan amallar navbati
const dbPromise = openDB('ecode-mobile', 1, {
  upgrade(db) {
    db.createObjectStore('kv');
    const ob = db.createObjectStore('outbox', { keyPath: 'id' });
    ob.createIndex('created_at', 'created_at');
  },
});

export async function kvGet(key) { return (await dbPromise).get('kv', key); }
export async function kvSet(key, value) { return (await dbPromise).put('kv', { value, saved_at: Date.now() }, key); }
export async function kvDel(key) { return (await dbPromise).delete('kv', key); }

export async function outboxAll() { return (await dbPromise).getAllFromIndex('outbox', 'created_at'); }
export async function outboxPut(item) { return (await dbPromise).put('outbox', item); }
export async function outboxDel(id) { return (await dbPromise).delete('outbox', id); }

/** Chiqishda (boshqa xodim kirishi) — shaxsiy ma'lumot telefonda qolmasin */
export async function wipeAll() {
  const db = await dbPromise;
  await db.clear('kv');
  await db.clear('outbox');
}
