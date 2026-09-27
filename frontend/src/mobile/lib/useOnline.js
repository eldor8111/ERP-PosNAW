import { useEffect, useState } from 'react';
import { Network } from '@capacitor/network';
import { subscribe } from '../offline/outbox';

/** { online, pending, failed } — sarlavhadagi holat belgisi uchun */
export default function useSyncState() {
  const [online, setOnline] = useState(true);
  const [items, setItems] = useState([]);

  useEffect(() => {
    Network.getStatus().then(s => setOnline(s.connected)).catch(() => setOnline(navigator.onLine));
    let handle;
    Network.addListener('networkStatusChange', s => setOnline(s.connected)).then(h => { handle = h; }).catch(() => {});
    const unsub = subscribe(setItems);
    return () => { handle?.remove(); unsub(); };
  }, []);

  return {
    online,
    items,
    pending: items.filter(i => i.state === 'pending').length,
    failed: items.filter(i => i.state === 'failed').length,
  };
}
