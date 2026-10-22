import { useEffect, useRef, useState } from 'react';

/**
 * Ko'p markerli interaktiv xarita (jonli xodimlar, kunlik marshrut, rang-barang tashriflar).
 * VITE_YANDEX_MAPS_KEY bo'lsa Yandex, bo'lmasa Leaflet + OpenStreetMap.
 *
 * markers: [{
 *   id, lat, lng, label, color, title, htmlPopup,
 *   badge,        // 1, 2, 3... yoki '🛒', '💰', '❌', '🚪', '🚚', '📍', '🚀'
 *   isWarning,    // Masofa radiusdan tashqarida bo'lsa (qizil ogohlantirish)
 *   isLive,       // Jonli harakat (pulsatsiyalovchi nishon)
 *   subLabel,     // Kichik yozuv (masalan vaqt: 09:45)
 * }]
 * path: [[lat, lng], ...] — xodim yurgan GPS yo'li (chiziq)
 * fitKey: o'zgarganda xarita barcha nuqtalarni ko'rsatadigan qilib moslashadi
 * activeMarkerId: tanlangan markerni markazga olib popapni ochadi
 * onMarkerClick: marker bosilganda chaqiriladi
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

export default function MultiMap({
  markers = [],
  path = [],
  height = 520,
  fitKey,
  activeMarkerId = null,
  onMarkerClick = null,
  pathColor = '#2563EB',
}) {
  const el = useRef(null);
  const api = useRef(null); // { render(markers, path, fit), focus(id), destroy() }
  const [engine, setEngine] = useState(YANDEX_KEY ? 'yandex' : 'osm');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const initYandex = async () => {
      const ymaps = await loadYandex();
      if (cancelled || !el.current) return;
      const map = new ymaps.Map(el.current, { center: CENTER, zoom: 12, controls: ['zoomControl', 'fullscreenControl'] });
      const layer = new ymaps.GeoObjectCollection();
      map.geoObjects.add(layer);

      const markerMap = new Map();

      api.current = {
        render(ms, pth, fit) {
          layer.removeAll();
          markerMap.clear();

          // Yo'l (polyline)
          if (pth && pth.length > 1) {
            // Shadow line
            layer.add(new ymaps.Polyline(pth, {}, { strokeColor: pathColor, strokeWidth: 8, strokeOpacity: 0.25 }));
            // Main line
            layer.add(new ymaps.Polyline(pth, {}, { strokeColor: pathColor, strokeWidth: 4, strokeOpacity: 0.9 }));
          }

          ms.forEach((m, idx) => {
            const pinColor = m.color || '#2563EB';
            const caption = m.badge != null ? `${m.badge}. ${m.label || ''}` : (m.label || '');
            const balloonContent = m.htmlPopup || m.title || `<b>${esc(m.label)}</b>`;

            const placemark = new ymaps.Placemark(
              [m.lat, m.lng],
              {
                iconCaption: caption,
                balloonContent: balloonContent,
                hintContent: m.label,
              },
              {
                preset: m.isWarning ? 'islands#redDotIconWithCaption' : 'islands#circleDotIcon',
                iconColor: pinColor,
              }
            );

            if (onMarkerClick) {
              placemark.events.add('click', () => onMarkerClick(m.id));
            }

            layer.add(placemark);
            markerMap.set(String(m.id), placemark);
          });

          if (fit && (ms.length || (pth && pth.length > 1))) {
            const b = layer.getBounds();
            if (b) map.setBounds(b, { checkZoomRange: true, zoomMargin: 45 });
          }
        },
        focus(id) {
          const pm = markerMap.get(String(id));
          if (pm) {
            const coords = pm.geometry.getCoordinates();
            map.panTo(coords, { flying: true });
            pm.balloon.open();
          }
        },
        destroy: () => map.destroy(),
      };
      setReady(true);
    };

    const initOsm = async () => {
      const [{ default: L }] = await Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')]);
      if (cancelled || !el.current) return;

      const map = L.map(el.current, { zoomControl: true }).setView(CENTER, 12);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap',
      }).addTo(map);

      const layer = L.layerGroup().addTo(map);
      const markerMap = new Map();

      api.current = {
        render(ms, pth, fit) {
          layer.clearLayers();
          markerMap.clear();
          const bounds = [];

          // Trek chizig'i (zamonaviy soya + asosiy polyline)
          if (pth && pth.length > 1) {
            // Glow shadow
            L.polyline(pth, { color: pathColor, weight: 7, opacity: 0.22, lineCap: 'round', lineJoin: 'round' }).addTo(layer);
            // Crisp route
            L.polyline(pth, { color: pathColor, weight: 3.5, opacity: 0.9, lineCap: 'round', lineJoin: 'round' }).addTo(layer);
            bounds.push(...pth);
          }

          ms.forEach((m, idx) => {
            const pinColor = m.color || '#2563EB';
            const badgeContent = m.badge != null ? String(m.badge) : (idx + 1);
            const isWarn = !!m.isWarning;
            const isLive = !!m.isLive;

            // HTML Custom Pin
            const pulseHtml = isLive
              ? `<span style="position:absolute;inset:-6px;border-radius:999px;background:${pinColor};opacity:0.4;animation:ping 1.5s cubic-bezier(0,0,0.2,1) infinite;"></span>`
              : isWarn
              ? `<span style="position:absolute;inset:-5px;border-radius:999px;background:#EF4444;opacity:0.45;animation:pulse 2s infinite;"></span>`
              : '';

            const iconHtml = `
              <div style="position:relative;display:inline-flex;align-items:center;cursor:pointer;filter:drop-shadow(0 3px 6px rgba(0,0,0,0.25));transform:translate(-50%, -100%);">
                ${pulseHtml}
                <div style="
                  display:flex;align-items:center;gap:5px;
                  background:${pinColor};color:#ffffff;
                  border:2px solid #ffffff;border-radius:20px;
                  padding:3px 7px 3px 5px;
                  box-shadow:0 2px 8px rgba(0,0,0,0.18);
                  font-family:Inter,system-ui,sans-serif;
                ">
                  <span style="
                    display:flex;align-items:center;justify-content:center;
                    min-width:18px;height:18px;border-radius:999px;
                    background:#ffffff;color:${pinColor};
                    font-size:10px;font-weight:800;padding:0 3px;
                  ">${esc(badgeContent)}</span>
                  ${m.label ? `<span style="font-size:11px;font-weight:700;white-space:nowrap;max-width:140px;overflow:hidden;text-overflow:ellipsis;">${esc(m.label)}</span>` : ''}
                  ${m.subLabel ? `<span style="font-size:10px;opacity:0.85;white-space:nowrap;">${esc(m.subLabel)}</span>` : ''}
                </div>
                <!-- Pin Pointer Arrow -->
                <div style="position:absolute;bottom:-6px;left:50%;transform:translateX(-50%);width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:6px solid ${pinColor};"></div>
              </div>
            `;

            const icon = L.divIcon({
              className: 'custom-multi-marker',
              html: iconHtml,
              iconSize: [0, 0],
              iconAnchor: [0, 0],
            });

            const mk = L.marker([m.lat, m.lng], { icon }).addTo(layer);

            // Popap
            const popupHtml = m.htmlPopup || (
              `<div style="font-family:Inter,system-ui,sans-serif;min-width:190px;padding:4px 2px;">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;gap:6px;">
                  <span style="font-size:11px;font-weight:700;color:${pinColor};">#${badgeContent}</span>
                  ${m.subLabel ? `<span style="font-size:10px;color:#64748B;">${esc(m.subLabel)}</span>` : ''}
                </div>
                <div style="font-size:13px;font-weight:700;color:#0F172A;margin-bottom:3px;">${esc(m.label || m.title || 'Nuqta')}</div>
                ${m.title && m.title !== m.label ? `<div style="font-size:11px;color:#475569;margin-top:2px;">${m.title}</div>` : ''}
              </div>`
            );

            mk.bindPopup(popupHtml, { maxWidth: 320 });

            if (onMarkerClick) {
              mk.on('click', () => onMarkerClick(m.id));
            }

            bounds.push([m.lat, m.lng]);
            markerMap.set(String(m.id), mk);
          });

          if (fit && bounds.length) {
            map.fitBounds(bounds, { padding: [45, 45], maxZoom: 16 });
          }
        },
        focus(id) {
          const mk = markerMap.get(String(id));
          if (mk) {
            map.flyTo(mk.getLatLng(), Math.max(map.getZoom(), 15), { duration: 0.8 });
            mk.openPopup();
          }
        },
        destroy: () => map.remove(),
      };

      setTimeout(() => map.invalidateSize(), 150);
      setReady(true);
    };

    (engine === 'yandex' ? initYandex() : initOsm()).catch(() => {
      if (!cancelled && engine === 'yandex') setEngine('osm');
    });

    return () => {
      cancelled = true;
      api.current?.destroy();
      api.current = null;
      setReady(false);
    };
  }, [engine, pathColor, onMarkerClick]);

  // Ma'lumot yangilanganda chizish
  const lastFit = useRef(null);
  useEffect(() => {
    if (!ready || !api.current) return;
    const fit = lastFit.current !== fitKey;
    lastFit.current = fitKey;
    api.current.render(markers, path, fit);
  }, [ready, markers, path, fitKey]);

  // Faol marker o'zgarsa unga fokus qilish
  useEffect(() => {
    if (!ready || !api.current || !activeMarkerId) return;
    api.current.focus(activeMarkerId);
  }, [ready, activeMarkerId]);

  return (
    <div
      ref={el}
      className="w-full rounded-2xl overflow-hidden border border-slate-200 bg-slate-50 relative shadow-inner"
      style={{ height }}
    />
  );
}
