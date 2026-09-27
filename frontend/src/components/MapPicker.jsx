import { useEffect, useRef, useState } from 'react';
import { Search, LocateFixed, Loader2 } from 'lucide-react';
import { useLang } from '../context/LangContext';

/**
 * Xaritadan nuqta tanlash. VITE_YANDEX_MAPS_KEY bo'lsa Yandex Maps 2.1,
 * bo'lmasa Leaflet + OpenStreetMap (kalitsiz). Ikkala rejimda ham:
 * manzil qidirish, xaritani bosib/markerni sudrab tanlash, "Mening
 * joylashuvim", tanlangan nuqta bo'yicha manzilni avtomatik aniqlash.
 *
 * value: { lat, lng } | null
 * onChange({ lat, lng, address })  — address topilmasa null
 */
const YANDEX_KEY = import.meta.env.VITE_YANDEX_MAPS_KEY || '';
const DEFAULT_CENTER = [41.311081, 69.240562]; // Toshkent
const round7 = (n) => Math.round(n * 1e7) / 1e7;

let yandexPromise = null;
function loadYandex(lang) {
  if (window.ymaps?.ready) return new Promise(res => window.ymaps.ready(() => res(window.ymaps)));
  if (!yandexPromise) {
    yandexPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = `https://api-maps.yandex.ru/2.1/?apikey=${encodeURIComponent(YANDEX_KEY)}&lang=${lang}`;
      s.async = true;
      s.onload = () => window.ymaps.ready(() => resolve(window.ymaps));
      s.onerror = () => { yandexPromise = null; reject(new Error('yandex-load')); };
      document.head.appendChild(s);
    });
  }
  return yandexPromise;
}

async function loadLeaflet() {
  const [{ default: L }] = await Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')]);
  return L;
}

// ── Geokodlash (koordinata ⇄ manzil) ────────────────────────────────────────
async function reverseGeocode(engine, lat, lng, lang) {
  try {
    if (engine === 'yandex') {
      const res = await window.ymaps.geocode([lat, lng], { results: 1 });
      return res.geoObjects.get(0)?.getAddressLine() || null;
    }
    const r = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&accept-language=${lang}`);
    const j = await r.json();
    return j.display_name || null;
  } catch { return null; }
}

async function forwardGeocode(engine, query, lang) {
  if (engine === 'yandex') {
    const res = await window.ymaps.geocode(query, { results: 1 });
    const obj = res.geoObjects.get(0);
    if (!obj) return null;
    const [lat, lng] = obj.geometry.getCoordinates();
    return { lat, lng, address: obj.getAddressLine() };
  }
  const r = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=uz&accept-language=${lang}&q=${encodeURIComponent(query)}`);
  const j = await r.json();
  if (!j.length) return null;
  return { lat: Number(j[0].lat), lng: Number(j[0].lon), address: j[0].display_name };
}

export default function MapPicker({ value, onChange, height = 260, readOnly = false }) {
  const { t, lang } = useLang();
  const elRef = useRef(null);
  const mapRef = useRef(null);      // { setPoint(lat,lng,pan), destroy() }
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const [engine, setEngine] = useState(YANDEX_KEY ? 'yandex' : 'osm');
  const [ready, setReady] = useState(false);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const geoLang = lang === 'en' ? 'en' : lang === 'ru' ? 'ru' : 'uz';

  const pick = async (lat, lng, pan = false, knownAddress) => {
    lat = round7(lat); lng = round7(lng);
    mapRef.current?.setPoint(lat, lng, pan);
    const address = knownAddress ?? await reverseGeocode(engine, lat, lng, geoLang);
    onChangeRef.current?.({ lat, lng, address });
  };
  const pickRef = useRef(pick);
  pickRef.current = pick;

  // Xaritani yaratish
  useEffect(() => {
    let cancelled = false;
    const start = value?.lat != null ? [Number(value.lat), Number(value.lng)] : DEFAULT_CENTER;
    const zoom = value?.lat != null ? 16 : 11;

    const initYandex = async () => {
      const ymaps = await loadYandex(lang === 'en' ? 'en_US' : 'ru_RU');
      if (cancelled || !elRef.current) return;
      const map = new ymaps.Map(elRef.current, { center: start, zoom, controls: ['zoomControl', 'fullscreenControl'] });
      let mark = null;
      const setPoint = (lat, lng, pan) => {
        if (!mark) {
          mark = new ymaps.Placemark([lat, lng], {}, { preset: 'islands#redDotIcon', draggable: !readOnly });
          mark.events.add('dragend', () => { const [a, b] = mark.geometry.getCoordinates(); pickRef.current(a, b); });
          map.geoObjects.add(mark);
        } else mark.geometry.setCoordinates([lat, lng]);
        if (pan) map.setCenter([lat, lng], 16);
      };
      if (!readOnly) map.events.add('click', e => { const [a, b] = e.get('coords'); pickRef.current(a, b); });
      if (value?.lat != null) setPoint(start[0], start[1]);
      mapRef.current = { setPoint, destroy: () => map.destroy() };
      setReady(true);
    };

    const initOsm = async () => {
      const L = await loadLeaflet();
      if (cancelled || !elRef.current) return;
      const map = L.map(elRef.current, { zoomControl: true }).setView(start, zoom);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, attribution: '&copy; OpenStreetMap',
      }).addTo(map);
      const icon = L.divIcon({
        className: '',
        html: '<div style="width:18px;height:18px;border-radius:50%;background:#e02424;border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>',
        iconSize: [18, 18], iconAnchor: [9, 9],
      });
      let mark = null;
      const setPoint = (lat, lng, pan) => {
        if (!mark) {
          mark = L.marker([lat, lng], { icon, draggable: !readOnly }).addTo(map);
          mark.on('dragend', () => { const p = mark.getLatLng(); pickRef.current(p.lat, p.lng); });
        } else mark.setLatLng([lat, lng]);
        if (pan) map.setView([lat, lng], 16);
      };
      if (!readOnly) map.on('click', e => pickRef.current(e.latlng.lat, e.latlng.lng));
      if (value?.lat != null) setPoint(start[0], start[1]);
      // Modal ichida ochilganda o'lcham to'g'ri hisoblansin
      setTimeout(() => map.invalidateSize(), 150);
      mapRef.current = { setPoint, destroy: () => map.remove() };
      setReady(true);
    };

    setReady(false);
    (engine === 'yandex' ? initYandex() : initOsm()).catch(() => {
      // Yandex yuklanmasa (kalit noto'g'ri/tarmoq) — OSM ga o'tamiz
      if (!cancelled && engine === 'yandex') setEngine('osm');
      else if (!cancelled) setErr(t('map.loadError'));
    });
    return () => { cancelled = true; mapRef.current?.destroy(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engine]);

  // Tashqaridan value o'zgarsa (masalan Telegramdan kelgan lokatsiya) markerni siljitamiz
  useEffect(() => {
    if (ready && value?.lat != null) mapRef.current?.setPoint(Number(value.lat), Number(value.lng), true);
  }, [ready, value?.lat, value?.lng]);

  const search = async () => {
    if (!query.trim()) return;
    setBusy(true); setErr('');
    try {
      const r = await forwardGeocode(engine, query.trim(), geoLang);
      if (r) await pick(r.lat, r.lng, true, r.address);
      else setErr(t('map.notFound'));
    } catch { setErr(t('map.notFound')); }
    finally { setBusy(false); }
  };

  const locateMe = () => {
    if (!navigator.geolocation) return;
    setBusy(true); setErr('');
    navigator.geolocation.getCurrentPosition(
      async (pos) => { await pick(pos.coords.latitude, pos.coords.longitude, true); setBusy(false); },
      () => { setErr(t('map.geoDenied')); setBusy(false); },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  return (
    <div className="space-y-2">
      {!readOnly && (
        <div className="flex gap-2">
          <div className="flex-1 flex items-center gap-2 px-3 border border-line rounded-xl bg-surface focus-within:ring-2 focus-within:ring-brand/40">
            <Search className="size-4 text-ink-300 shrink-0" />
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); search(); } }}
              placeholder={t('map.searchPlaceholder')}
              className="flex-1 py-2.5 text-sm bg-transparent outline-none min-w-0"
            />
            {busy && <Loader2 className="size-4 text-ink-300 animate-spin" />}
          </div>
          <button type="button" onClick={locateMe} title={t('map.myLocation')}
            className="px-3 border border-line rounded-xl text-ink-500 hover:bg-surface-sunken">
            <LocateFixed className="size-4" />
          </button>
        </div>
      )}
      <div className="relative rounded-xl overflow-hidden border border-line" style={{ height }}>
        <div ref={elRef} className="absolute inset-0" />
        {!ready && <div className="absolute inset-0 flex items-center justify-center bg-surface-sunken text-sm text-ink-300">{t('map.loading')}</div>}
      </div>
      <div className="flex items-center justify-between text-[11px] text-ink-300">
        <span>{err ? <span className="text-danger">{err}</span> : (!readOnly && t('map.hint'))}</span>
        <span>{engine === 'yandex' ? 'Yandex' : 'OpenStreetMap'}</span>
      </div>
    </div>
  );
}

