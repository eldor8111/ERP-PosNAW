import { useEffect, useRef, useState } from 'react';

/**
 * Ko'p markerli xarita (jonli xodimlar, kunlik trek). MapPicker kabi:
 * VITE_YANDEX_MAPS_KEY bo'lsa Yandex, bo'lmasa Leaflet + OSM.
 *
 * markers: [{ id, lat, lng, label, color, title }]
 * path: [[lat, lng], ...] — chiziq (kunlik yo'l)
 * fitKey: o'zgarganda xarita barcha nuqtalarni ko'rsatadigan qilib moslashadi
 */
const YANDEX_KEY = import.meta.env.VITE_YANDEX_MAPS_KEY || '';
const CENTER = [41.311081, 69.240562];

let yPromise = null;
function loadYandex() {
  if (window.ymaps?.ready) return new Promise(r => window.ymaps.ready(() => r(window.ymaps)));
  if (!yPromise) {
    yPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = `https://api-maps.yandex.ru/2.1/?apikey=${encodeURIComponent(YANDEX_KEY)}&lang=ru_RU`;
      s.onload = () => window.ymaps.ready(() => resolve(window.ymaps));
      s.onerror = () => { yPromise = null; reject(new Error('yandex')); };
      document.head.appendChild(s);
    });
  }
  return yPromise;
}

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export default function MultiMap({ markers = [], path = [], height = 420, fitKey }) {
  const el = useRef(null);
  const api = useRef(null); // { render(markers, path, fit), destroy() }
  const [engine, setEngine] = useState(YANDEX_KEY ? 'yandex' : 'osm');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const initYandex = async () => {
      const ymaps = await loadYandex();
      if (cancelled || !el.current) return;
      const map = new ymaps.Map(el.current, { center: CENTER, zoom: 11, controls: ['zoomControl', 'fullscreenControl'] });
      const layer = new ymaps.GeoObjectCollection();
      map.geoObjects.add(layer);
      api.current = {
        render(ms, pth, fit) {
          layer.removeAll();
          if (pth.length > 1) layer.add(new ymaps.Polyline(pth, {}, { strokeColor: '#2554C7', strokeWidth: 4, strokeOpacity: 0.7 }));
          ms.forEach(m => layer.add(new ymaps.Placemark([m.lat, m.lng],
            { iconCaption: m.label, balloonContent: m.title || esc(m.label) },
            { preset: 'islands#circleDotIcon', iconColor: m.color || '#2554C7' })));
          if (fit && (ms.length || pth.length > 1)) map.setBounds(layer.getBounds(), { checkZoomRange: true, zoomMargin: 40 });
        },
        destroy: () => map.destroy(),
      };
      setReady(true);
    };
    const initOsm = async () => {
      const [{ default: L }] = await Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')]);
      if (cancelled || !el.current) return;
      const map = L.map(el.current).setView(CENTER, 11);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap' }).addTo(map);
      const layer = L.layerGroup().addTo(map);
      api.current = {
        render(ms, pth, fit) {
          layer.clearLayers();
          const bounds = [];
          if (pth.length > 1) { L.polyline(pth, { color: '#2554C7', weight: 4, opacity: 0.7 }).addTo(layer); bounds.push(...pth); }
          ms.forEach(m => {
            const icon = L.divIcon({
              className: '',
              html: `<div style="display:flex;align-items:center;gap:4px;white-space:nowrap"><span style="width:14px;height:14px;border-radius:50%;background:${m.color || '#2554C7'};border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4)"></span>${m.label ? `<span style="font:600 11px Inter,sans-serif;background:#fff;padding:1px 5px;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.2)">${esc(m.label)}</span>` : ''}</div>`,
              iconAnchor: [7, 7],
            });
            const mk = L.marker([m.lat, m.lng], { icon }).addTo(layer);
            if (m.title) mk.bindPopup(m.title);
            bounds.push([m.lat, m.lng]);
          });
          if (fit && bounds.length) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
        },
        destroy: () => map.remove(),
      };
      setTimeout(() => map.invalidateSize(), 150);
      setReady(true);
    };
    (engine === 'yandex' ? initYandex() : initOsm()).catch(() => { if (!cancelled && engine === 'yandex') setEngine('osm'); });
    return () => { cancelled = true; api.current?.destroy(); api.current = null; setReady(false); };
  }, [engine]);

  // Ma'lumot o'zgarsa qayta chizamiz; fitKey o'zgargandagina ko'rinishni moslaymiz
  const lastFit = useRef(null);
  useEffect(() => {
    if (!ready || !api.current) return;
    const fit = lastFit.current !== fitKey;
    lastFit.current = fitKey;
    api.current.render(markers, path, fit);
  }, [ready, markers, path, fitKey]);

  return <div ref={el} className="w-full rounded-2xl overflow-hidden border border-line bg-surface-sunken" style={{ height }} />;
}
