const DB_NAME = 'ERP_POS_DB';
const DB_VERSION = 1;

// Stores
const STORES = {
  PRODUCTS: 'products',
  PENDING_SALES: 'pending_sales',
  CONFIG: 'config' // To store auth token/last sync time
};

export const initDB = () => {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORES.PRODUCTS)) {
        db.createObjectStore(STORES.PRODUCTS, { keyPath: 'barcode' });
      }
      if (!db.objectStoreNames.contains(STORES.PENDING_SALES)) {
        db.createObjectStore(STORES.PENDING_SALES, { keyPath: 'id', autoIncrement: true });
      }
      if (!db.objectStoreNames.contains(STORES.CONFIG)) {
        db.createObjectStore(STORES.CONFIG, { keyPath: 'key' });
      }
    };

    request.onsuccess = (e) => resolve(e.target.result);
    request.onerror = (e) => reject(e.target.error);
  });
};

// --- Products Sync ---
export const saveProductsLocally = async (products) => {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORES.PRODUCTS, 'readwrite');
    const store = tx.objectStore(STORES.PRODUCTS);
    
    products.forEach(p => {
      if (p.barcode) store.put(p);
    });

    tx.oncomplete = () => resolve();
    tx.onerror = (e) => reject(e.target.error);
  });
};

export const getLocalProductByBarcode = async (barcode) => {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORES.PRODUCTS, 'readonly');
    const store = tx.objectStore(STORES.PRODUCTS);
    const request = store.get(barcode);
    
    request.onsuccess = (e) => resolve(e.target.result);
    request.onerror = (e) => reject(e.target.error);
  });
};

// --- Sales Sync ---
export const saveSaleOffline = async (saleParams) => {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORES.PENDING_SALES, 'readwrite');
    const store = tx.objectStore(STORES.PENDING_SALES);
    
    const request = store.add({ ...saleParams, timestamp: new Date().toISOString() });
    
    request.onsuccess = () => resolve();
    request.onerror = (e) => reject(e.target.error);
  });
};

export const getPendingSales = async () => {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORES.PENDING_SALES, 'readonly');
    const store = tx.objectStore(STORES.PENDING_SALES);
    const request = store.getAll();
    
    request.onsuccess = (e) => resolve(e.target.result);
    request.onerror = (e) => reject(e.target.error);
  });
};

export const clearPendingSale = async (id) => {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORES.PENDING_SALES, 'readwrite');
    const store = tx.objectStore(STORES.PENDING_SALES);
    const request = store.delete(id);
    
    request.onsuccess = () => resolve();
    request.onerror = (e) => reject(e.target.error);
  });
};
