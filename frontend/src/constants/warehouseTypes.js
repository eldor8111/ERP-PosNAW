// Ombor turlari — backend `WarehouseType` enum bilan bir xil (app/models/warehouse.py).
// Filiallar, Ombor va Warehouse sahifalari shu ro'yxatdan foydalanadi (T3.1).
// `labelKey` — i18n kaliti (t(labelKey)); `color` — tur belgisi uchun Tailwind sinflari.
export const WAREHOUSE_TYPES = [
  { value: 'main', labelKey: 'branch.typeMain', color: 'bg-blue-50 text-blue-700 border-blue-200' },
  { value: 'shop', labelKey: 'branch.typeShop', color: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  { value: 'transit', labelKey: 'branch.typeTransit', color: 'bg-amber-50 text-amber-700 border-amber-200' },
  { value: 'returns', labelKey: 'branch.typeReturns', color: 'bg-rose-50 text-rose-700 border-rose-200' },
  { value: 'raw_material', labelKey: 'branch.typeRawMaterial', color: 'bg-orange-50 text-orange-700 border-orange-200' },
  { value: 'wip', labelKey: 'branch.typeWip', color: 'bg-violet-50 text-violet-700 border-violet-200' },
];

export const WAREHOUSE_TYPE_BY_VALUE = Object.fromEntries(WAREHOUSE_TYPES.map(wt => [wt.value, wt]));
