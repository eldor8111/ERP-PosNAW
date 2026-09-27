/** Koordinata bo'yicha Yandex Maps'da ochish havolasi */
export const yandexMapsUrl = (lat, lng) => `https://yandex.uz/maps/?pt=${lng},${lat}&z=17&l=map`;

/** Bir nechta nuqta bo'yicha Yandex Maps marshruti (tartib bilan) */
export const yandexRouteUrl = (points) =>
  `https://yandex.uz/maps/?rtext=${points.map(p => `${p.lat},${p.lng}`).join('~')}&rtt=auto`;
