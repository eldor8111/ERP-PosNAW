import { useState, useEffect, useCallback, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Plus, Search, Pencil, Trash2, ClipboardList, X } from 'lucide-react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import useCompanyFeatures from '../../../hooks/useCompanyFeatures';
import { fmtQty } from '../../../utils/qty';

// R1: restoran menyusi — taomlar, yarim tayyorlar, ingredientlar, tovarlar, sexlar va texnologik kartalar.
// Backend: app/routers/restaurant_menu.py. Marshrut App.jsx'da FeatureGate feature="restaurant" bilan o'ralgan.

const TABS = [
  { key: 'dish', label: 'restMenu.tabDish' },
  { key: 'semi', label: 'restMenu.tabSemi' },
  { key: 'ingredient', label: 'restMenu.tabIngredient' },
  { key: 'goods', label: 'restMenu.tabGoods' },
  { key: 'stations', label: 'restMenu.tabStations' },
];
const TAB_KEYS = TABS.map(x => x.key);
const UNITS = ['porsiya', 'dona', 'kg', 'g', 'l', 'ml'];
const DEFAULT_UNIT = { dish: 'porsiya', semi: 'kg', ingredient: 'kg', goods: 'dona' };
const HAS_CARD = ['dish', 'semi'];
const HAS_PRICE = ['dish', 'goods'];
const HAS_COST = ['semi', 'ingredient', 'goods'];
const HAS_STATION = ['dish', 'semi'];

const money = v => (Number(v) || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 0 });
const num = v => (v === '' || v === null || v === undefined ? null : Number(String(v).replace(',', '.')));

const inputCls = 'w-full px-3 py-2 border border-slate-200 rounded-lg bg-white text-sm text-slate-800 focus:outline-none focus:border-blue-500';
const btnPrimary = 'inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold disabled:opacity-50';
const btnGhost = 'inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-sm font-semibold';

function Modal({ title, onClose, children, wide }) {
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-start justify-center overflow-y-auto p-4" onMouseDown={onClose}>
      <div className={`bg-white rounded-xl border border-slate-200 w-full ${wide ? 'max-w-4xl' : 'max-w-lg'} mt-10`}
           onMouseDown={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
          <h3 className="text-base font-bold text-slate-800">{title}</h3>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-slate-600 mb-1">{label}</span>
      {children}
    </label>
  );
}

// ───────────────────────── Mahsulot formasi ─────────────────────────

function ItemModal({ kind, item, categories, stations, onClose, onSaved, t }) {
  const [form, setForm] = useState(() => ({
    name: item?.name || '',
    unit: item?.unit || DEFAULT_UNIT[kind],
    category_id: item?.category_id ?? '',
    station_id: item?.station_id ?? '',
    sale_price: item ? item.sale_price : '',
    cost_price: item ? item.cost_price : '',
    barcode: '',
    is_active: item ? item.is_active : true,
  }));
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const save = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { toast.error(t('restMenu.nameRequired')); return; }
    const body = {
      name: form.name.trim(), unit: form.unit,
      category_id: form.category_id === '' ? null : Number(form.category_id),
      is_active: form.is_active,
    };
    if (HAS_STATION.includes(kind)) body.station_id = form.station_id === '' ? null : Number(form.station_id);
    if (HAS_PRICE.includes(kind)) body.sale_price = num(form.sale_price) ?? 0;
    if (HAS_COST.includes(kind)) body.cost_price = num(form.cost_price) ?? 0;
    if (!item) {
      body.kind = kind;
      if (kind === 'goods' && form.barcode.trim()) body.barcode = form.barcode.trim();
    }
    setSaving(true);
    try {
      if (item) await api.put(`/restaurant/menu/items/${item.id}`, body);
      else await api.post('/restaurant/menu/items', body);
      toast.success(t('restMenu.saved'));
      onSaved();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('restMenu.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={item ? t('restMenu.editItem') : t(`restMenu.add.${kind}`)} onClose={onClose}>
      <form onSubmit={save} className="space-y-3">
        <Field label={t('restMenu.name')}>
          <input className={inputCls} value={form.name} onChange={e => set('name', e.target.value)} autoFocus maxLength={200} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('restMenu.unit')}>
            <select className={inputCls} value={form.unit} onChange={e => set('unit', e.target.value)}>
              {UNITS.map(u => <option key={u} value={u}>{u}</option>)}
            </select>
          </Field>
          <Field label={t('restMenu.category')}>
            <select className={inputCls} value={form.category_id} onChange={e => set('category_id', e.target.value)}>
              <option value="">{t('restMenu.none')}</option>
              {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
        </div>
        {HAS_STATION.includes(kind) && (
          <Field label={t('restMenu.station')}>
            <select className={inputCls} value={form.station_id} onChange={e => set('station_id', e.target.value)}>
              <option value="">{t('restMenu.stationFromCategory')}</option>
              {stations.filter(s => s.is_active).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
        )}
        <div className="grid grid-cols-2 gap-3">
          {HAS_PRICE.includes(kind) && (
            <Field label={t('restMenu.salePrice')}>
              <input className={inputCls} inputMode="decimal" value={form.sale_price} onChange={e => set('sale_price', e.target.value)} />
            </Field>
          )}
          {HAS_COST.includes(kind) && (
            <Field label={kind === 'semi' ? t('restMenu.costPriceSemi') : t('restMenu.costPrice')}>
              <input className={inputCls} inputMode="decimal" value={form.cost_price} onChange={e => set('cost_price', e.target.value)} />
            </Field>
          )}
        </div>
        {!item && kind === 'goods' && (
          <Field label={t('restMenu.barcode')}>
            <input className={inputCls} value={form.barcode} onChange={e => set('barcode', e.target.value)} maxLength={50} />
          </Field>
        )}
        {item && (
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={form.is_active} onChange={e => set('is_active', e.target.checked)} />
            {t('restMenu.active')}
          </label>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className={btnGhost} onClick={onClose}>{t('restMenu.cancel')}</button>
          <button type="submit" className={btnPrimary} disabled={saving}>{t('restMenu.save')}</button>
        </div>
      </form>
    </Modal>
  );
}

// ───────────────────────── Texnologik karta ─────────────────────────

function CardModal({ item, components, alertPct, onClose, onSaved, t }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [head, setHead] = useState({ output_qty: '1', output_weight_g: '', cooking_time_min: '', instructions: '' });
  const [rows, setRows] = useState([]);
  const [version, setVersion] = useState(null);
  const [versions, setVersions] = useState(null);
  const [pick, setPick] = useState('');

  const byId = useMemo(() => Object.fromEntries(components.map(c => [c.id, c])), [components]);

  useEffect(() => {
    let alive = true;
    api.get(`/restaurant/menu/items/${item.id}/card`).then(r => {
      if (!alive) return;
      const c = r.data.card;
      if (c) {
        setVersion(c.version);
        setHead({
          output_qty: String(c.output_qty ?? 1), output_weight_g: c.output_weight_g ?? '',
          cooking_time_min: c.cooking_time_min ?? '', instructions: c.instructions || '',
        });
        setRows(c.items.map(x => ({
          component_product_id: x.component_product_id, name: x.name, unit: x.unit, unit_cost: x.unit_cost,
          gross_qty: String(x.gross_qty), net_qty: x.net_qty ?? '', loss_cold_pct: x.loss_cold_pct ?? '',
          loss_hot_pct: x.loss_hot_pct ?? '',
        })));
      }
    }).catch(err => toast.error(err.response?.data?.detail || t('restMenu.loadFailed')))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [item.id, t]);

  const addRow = () => {
    const c = components.find(x => x.name.toLowerCase() === pick.trim().toLowerCase());
    if (!c) { toast.error(t('restMenu.pickFromList')); return; }
    if (c.id === item.id) { toast.error(t('restMenu.selfRef')); return; }
    if (rows.some(r => r.component_product_id === c.id)) { toast.error(t('restMenu.dupRow')); return; }
    setRows(rs => [...rs, { component_product_id: c.id, name: c.name, unit: c.unit, unit_cost: c.unit_cost,
      gross_qty: '', net_qty: '', loss_cold_pct: '', loss_hot_pct: '' }]);
    setPick('');
  };
  const setRow = (i, k, v) => setRows(rs => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const delRow = i => setRows(rs => rs.filter((_, j) => j !== i));

  const unitCostOf = r => (byId[r.component_product_id]?.unit_cost ?? r.unit_cost ?? 0);
  const total = rows.reduce((s, r) => s + (num(r.gross_qty) || 0) * unitCostOf(r), 0);
  const outQty = num(head.output_qty) || 1;
  const unitCost = total / outQty;
  const fc = item.kind === 'dish' && item.sale_price > 0 ? (unitCost / item.sale_price) * 100 : null;

  const save = async () => {
    if (!rows.length) { toast.error(t('restMenu.needRow')); return; }
    const body = {
      output_qty: item.kind === 'semi' ? num(head.output_qty) : 1,
      output_weight_g: num(head.output_weight_g),
      cooking_time_min: head.cooking_time_min === '' ? null : parseInt(head.cooking_time_min, 10),
      instructions: head.instructions,
      items: rows.map(r => ({
        component_product_id: r.component_product_id,
        gross_qty: num(r.gross_qty),
        net_qty: num(r.net_qty),
        loss_cold_pct: num(r.loss_cold_pct),
        loss_hot_pct: num(r.loss_hot_pct),
      })),
    };
    setSaving(true);
    try {
      const r = await api.put(`/restaurant/menu/items/${item.id}/card`, body);
      toast.success(`${t('restMenu.cardSaved')}: v${r.data.card.version}`);
      onSaved();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('restMenu.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const loadVersions = () => {
    api.get(`/restaurant/menu/items/${item.id}/card/versions`).then(r => setVersions(r.data))
      .catch(err => toast.error(err.response?.data?.detail || t('restMenu.loadFailed')));
  };

  return (
    <Modal wide title={`${t('restMenu.card')}: ${item.name}${version ? ` (v${version})` : ''}`} onClose={onClose}>
      {loading ? (
        <div className="py-10 text-center text-sm text-slate-500">{t('restMenu.loading')}</div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {item.kind === 'semi' && (
              <Field label={`${t('restMenu.outputQty')} (${item.unit})`}>
                <input className={inputCls} inputMode="decimal" value={head.output_qty} onChange={e => setHead(h => ({ ...h, output_qty: e.target.value }))} />
              </Field>
            )}
            <Field label={t('restMenu.outputWeight')}>
              <input className={inputCls} inputMode="decimal" value={head.output_weight_g} onChange={e => setHead(h => ({ ...h, output_weight_g: e.target.value }))} />
            </Field>
            <Field label={t('restMenu.cookingTime')}>
              <input className={inputCls} inputMode="numeric" value={head.cooking_time_min} onChange={e => setHead(h => ({ ...h, cooking_time_min: e.target.value }))} />
            </Field>
          </div>

          <div className="flex gap-2">
            <input className={inputCls} list="rest-card-components" value={pick} placeholder={t('restMenu.addIngredient')}
                   onChange={e => setPick(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addRow(); } }} />
            <datalist id="rest-card-components">
              {components.filter(c => c.id !== item.id).map(c => <option key={c.id} value={c.name} />)}
            </datalist>
            <button type="button" className={btnGhost} onClick={addRow}><Plus className="w-4 h-4" />{t('restMenu.add')}</button>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="text-left px-3 py-2">{t('restMenu.ingredient')}</th>
                  <th className="text-right px-2 py-2 w-24">{t('restMenu.gross')}</th>
                  <th className="text-right px-2 py-2 w-24">{t('restMenu.net')}</th>
                  <th className="text-right px-2 py-2 w-20">{t('restMenu.lossCold')}</th>
                  <th className="text-right px-2 py-2 w-20">{t('restMenu.lossHot')}</th>
                  <th className="text-right px-3 py-2 w-28">{t('restMenu.lineCost')}</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr><td colSpan={7} className="px-3 py-6 text-center text-slate-400">{t('restMenu.noRows')}</td></tr>
                )}
                {rows.map((r, i) => {
                  const g = num(r.gross_qty) || 0;
                  return (
                    <tr key={r.component_product_id} className="border-t border-slate-100">
                      <td className="px-3 py-1.5">
                        <div className="font-medium text-slate-800">{r.name}</div>
                        <div className="text-[11px] text-slate-400">{money(unitCostOf(r))} / {r.unit}</div>
                      </td>
                      {['gross_qty', 'net_qty', 'loss_cold_pct', 'loss_hot_pct'].map(k => (
                        <td key={k} className="px-2 py-1.5">
                          <input className="w-full px-2 py-1 border border-slate-200 rounded text-right text-sm" inputMode="decimal"
                                 value={r[k]} onChange={e => setRow(i, k, e.target.value)} />
                        </td>
                      ))}
                      <td className="px-3 py-1.5 text-right tabular-nums">{money(g * unitCostOf(r))}</td>
                      <td className="pr-2">
                        <button type="button" onClick={() => delRow(i)} className="p-1 text-slate-400 hover:text-rose-600"><Trash2 className="w-4 h-4" /></button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-slate-500">{item.kind === 'semi' ? t('restMenu.grossHintSemi') : t('restMenu.grossHint')}</p>

          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <span className="text-slate-600">{t('restMenu.totalCost')}: <b className="text-slate-800 tabular-nums">{money(total)}</b></span>
            <span className="text-slate-600">{t('restMenu.unitCost')}: <b className="text-slate-800 tabular-nums">{money(unitCost)}</b> / {item.unit}</span>
            {fc !== null && (
              <span className="text-slate-600">{t('restMenu.foodCost')}: <b className={`tabular-nums ${fc > alertPct ? 'text-rose-600' : 'text-emerald-700'}`}>{fc.toFixed(1)}%</b></span>
            )}
          </div>

          <Field label={t('restMenu.instructions')}>
            <textarea className={`${inputCls} min-h-[70px]`} value={head.instructions} maxLength={5000}
                      onChange={e => setHead(h => ({ ...h, instructions: e.target.value }))} />
          </Field>

          {versions && (
            <div className="border border-slate-200 rounded-lg divide-y divide-slate-100 text-sm">
              {versions.map(v => (
                <div key={v.card.id} className="px-3 py-2 flex flex-wrap gap-x-4 gap-y-1">
                  <span className="font-semibold text-slate-800">v{v.card.version}</span>
                  <span className="text-slate-500">{v.card.created_at ? new Date(v.card.created_at).toLocaleString() : ''}</span>
                  <span className="text-slate-600">{t('restMenu.unitCost')}: {money(v.unit_cost)}</span>
                  <span className="text-slate-500">{v.card.items.map(x => `${x.name} ${fmtQty(x.gross_qty)}`).join(', ')}</span>
                  {v.is_active && <span className="text-emerald-700 font-semibold">{t('restMenu.current')}</span>}
                </div>
              ))}
            </div>
          )}

          <div className="flex justify-between gap-2 pt-1">
            <button type="button" className={btnGhost} onClick={loadVersions} disabled={!version}>{t('restMenu.history')}</button>
            <div className="flex gap-2">
              <button type="button" className={btnGhost} onClick={onClose}>{t('restMenu.cancel')}</button>
              <button type="button" className={btnPrimary} onClick={save} disabled={saving}>{t('restMenu.saveNewVersion')}</button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}

// ───────────────────────── Sexlar ─────────────────────────

function StationsPanel({ stations, categories, reload, t }) {
  const [newName, setNewName] = useState('');
  const [names, setNames] = useState({});

  const add = async () => {
    if (!newName.trim()) return;
    try {
      await api.post('/restaurant/stations', { name: newName.trim() });
      setNewName('');
      reload();
    } catch (err) { toast.error(err.response?.data?.detail || t('restMenu.saveFailed')); }
  };
  const update = async (s, body) => {
    try {
      await api.put(`/restaurant/stations/${s.id}`, body);
      reload();
    } catch (err) { toast.error(err.response?.data?.detail || t('restMenu.saveFailed')); }
  };
  const setCatStation = async (c, val) => {
    try {
      await api.put(`/restaurant/menu/categories/${c.id}`, { station_id: val === '' ? null : Number(val) });
      reload();
    } catch (err) { toast.error(err.response?.data?.detail || t('restMenu.saveFailed')); }
  };

  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <div className="bg-white border border-slate-200 rounded-xl">
        <div className="px-4 py-3 border-b border-slate-100">
          <h3 className="text-sm font-bold text-slate-800">{t('restMenu.stationsTitle')}</h3>
          <p className="text-xs text-slate-500 mt-0.5">{t('restMenu.stationsHint')}</p>
        </div>
        <div className="divide-y divide-slate-100">
          {stations.map(s => (
            <div key={s.id} className="px-4 py-2 flex items-center gap-2">
              <input className="flex-1 px-2 py-1 border border-transparent hover:border-slate-200 focus:border-blue-500 rounded text-sm font-medium text-slate-800"
                     value={names[s.id] ?? s.name}
                     onChange={e => setNames(n => ({ ...n, [s.id]: e.target.value }))}
                     onBlur={() => { const v = (names[s.id] ?? s.name).trim(); if (v && v !== s.name) update(s, { name: v }); }} />
              <label className="flex items-center gap-1 text-xs text-slate-600">
                <input type="checkbox" checked={s.kds_enabled} onChange={e => update(s, { kds_enabled: e.target.checked })} />KDS
              </label>
              <label className="flex items-center gap-1 text-xs text-slate-600">
                <input type="checkbox" checked={s.is_active} onChange={e => update(s, { is_active: e.target.checked })} />{t('restMenu.active')}
              </label>
            </div>
          ))}
        </div>
        <div className="px-4 py-3 border-t border-slate-100 flex gap-2">
          <input className={inputCls} value={newName} placeholder={t('restMenu.newStation')} maxLength={100}
                 onChange={e => setNewName(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') add(); }} />
          <button className={btnPrimary} onClick={add}><Plus className="w-4 h-4" />{t('restMenu.add')}</button>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl">
        <div className="px-4 py-3 border-b border-slate-100">
          <h3 className="text-sm font-bold text-slate-800">{t('restMenu.categoryStations')}</h3>
          <p className="text-xs text-slate-500 mt-0.5">{t('restMenu.categoryStationsHint')}</p>
        </div>
        <div className="divide-y divide-slate-100">
          {categories.map(c => (
            <div key={c.id} className="px-4 py-2 flex items-center gap-3">
              <span className="flex-1 text-sm text-slate-800">{c.name}</span>
              <select className="px-2 py-1 border border-slate-200 rounded text-sm" value={c.station_id ?? ''}
                      onChange={e => setCatStation(c, e.target.value)}>
                <option value="">{t('restMenu.none')}</option>
                {stations.filter(s => s.is_active).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ───────────────────────── Sahifa ─────────────────────────

export default function RestaurantMenu() {
  const { t } = useLang();
  const features = useCompanyFeatures();
  const alertPct = features?.restaurant_settings?.food_cost_alert_pct ?? 35;
  const location = useLocation();
  const navigate = useNavigate();

  const fromHash = useCallback(() => {
    const h = (location.hash || '').replace('#', '');
    return TAB_KEYS.includes(h) ? h : 'dish';
  }, [location.hash]);
  const [tab, setTab] = useState(fromHash);
  useEffect(() => { setTab(fromHash()); }, [fromHash]);

  const [items, setItems] = useState([]);
  const [components, setComponents] = useState([]);
  const [categories, setCategories] = useState([]);
  const [stations, setStations] = useState([]);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(false);
  const [edit, setEdit] = useState(null);      // {item|null}
  const [cardItem, setCardItem] = useState(null);

  const loadRefs = useCallback(() => {
    api.get('/restaurant/menu/categories').then(r => setCategories(r.data)).catch(() => {});
    api.get('/restaurant/stations').then(r => setStations(r.data)).catch(() => {});
  }, []);

  const loadItems = useCallback(() => {
    if (tab === 'stations') return;
    setLoading(true);
    api.get('/restaurant/menu/items', { params: { kind: tab, include_inactive: true } })
      .then(r => setItems(r.data))
      .catch(err => toast.error(err.response?.data?.detail || t('restMenu.loadFailed')))
      .finally(() => setLoading(false));
  }, [tab, t]);

  const loadComponents = useCallback(() => {
    api.get('/restaurant/menu/items', { params: { kind: 'ingredient,semi,goods' } })
      .then(r => setComponents(r.data)).catch(() => {});
  }, []);

  useEffect(() => { loadRefs(); loadComponents(); }, [loadRefs, loadComponents]);
  useEffect(() => { loadItems(); }, [loadItems]);

  const selectTab = key => {
    setTab(key);
    setQ('');
    navigate({ pathname: location.pathname, search: location.search, hash: `#${key}` }, { replace: true });
  };

  const stationName = id => stations.find(s => s.id === id)?.name || '';
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? items.filter(i => i.name.toLowerCase().includes(s)) : items;
  }, [items, q]);

  const remove = async (item) => {
    if (!window.confirm(`${t('restMenu.confirmDelete')}: ${item.name}?`)) return;
    try {
      await api.delete(`/restaurant/menu/items/${item.id}`);
      toast.success(t('restMenu.deleted'));
      loadItems();
      loadComponents();
    } catch (err) { toast.error(err.response?.data?.detail || t('restMenu.saveFailed')); }
  };

  const afterSave = () => { setEdit(null); setCardItem(null); loadItems(); loadComponents(); };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-800">{t('restMenu.title')}</h1>
        <p className="text-sm text-slate-500">{t('restMenu.desc')}</p>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map(x => (
          <button key={x.key} onClick={() => selectTab(x.key)}
                  className={`px-3 py-2 text-sm font-semibold border-b-2 -mb-px ${tab === x.key ? 'border-blue-600 text-blue-700' : 'border-transparent text-slate-500 hover:text-slate-700'}`}>
            {t(x.label)}
          </button>
        ))}
      </div>

      {tab === 'stations' ? (
        <StationsPanel stations={stations} categories={categories} reload={loadRefs} t={t} />
      ) : (
        <div className="bg-white border border-slate-200 rounded-xl">
          <div className="p-3 flex flex-wrap gap-2 items-center border-b border-slate-100">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input className={`${inputCls} pl-9`} value={q} onChange={e => setQ(e.target.value)} placeholder={t('restMenu.search')} />
            </div>
            <button className={btnPrimary} onClick={() => setEdit({ item: null })}><Plus className="w-4 h-4" />{t(`restMenu.add.${tab}`)}</button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="text-left px-4 py-2">{t('restMenu.name')}</th>
                  <th className="text-left px-3 py-2">{t('restMenu.category')}</th>
                  {HAS_STATION.includes(tab) && <th className="text-left px-3 py-2">{t('restMenu.station')}</th>}
                  {HAS_PRICE.includes(tab) && <th className="text-right px-3 py-2">{t('restMenu.salePrice')}</th>}
                  <th className="text-right px-3 py-2">{t('restMenu.unitCost')}</th>
                  {tab === 'dish' && <th className="text-right px-3 py-2">{t('restMenu.foodCost')}</th>}
                  <th className="w-32" />
                </tr>
              </thead>
              <tbody>
                {loading && <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">{t('restMenu.loading')}</td></tr>}
                {!loading && shown.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">{t('restMenu.empty')}</td></tr>
                )}
                {!loading && shown.map(it => (
                  <tr key={it.id} className={`border-t border-slate-100 ${it.is_active ? '' : 'opacity-50'}`}>
                    <td className="px-4 py-2">
                      <div className="font-medium text-slate-800">{it.name}</div>
                      <div className="text-[11px] text-slate-400">
                        {it.unit}
                        {HAS_CARD.includes(it.kind) && !it.has_card && <span className="ml-2 text-amber-600">{t('restMenu.noCard')}</span>}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-slate-600">{it.category_name || ''}</td>
                    {HAS_STATION.includes(tab) && (
                      <td className="px-3 py-2 text-slate-600">
                        {stationName(it.effective_station_id)}
                        {it.effective_station_id && !it.station_id && <span className="text-[11px] text-slate-400"> ({t('restMenu.byCategory')})</span>}
                      </td>
                    )}
                    {HAS_PRICE.includes(tab) && <td className="px-3 py-2 text-right tabular-nums">{money(it.sale_price)}</td>}
                    <td className="px-3 py-2 text-right tabular-nums">{money(it.unit_cost)}</td>
                    {tab === 'dish' && (
                      <td className={`px-3 py-2 text-right tabular-nums font-semibold ${it.food_cost_pct == null ? 'text-slate-300' : it.food_cost_pct > alertPct ? 'text-rose-600' : 'text-emerald-700'}`}>
                        {it.food_cost_pct == null ? '' : `${it.food_cost_pct}%`}
                      </td>
                    )}
                    <td className="px-3 py-2">
                      <div className="flex justify-end gap-1">
                        {HAS_CARD.includes(it.kind) && (
                          <button title={t('restMenu.card')} onClick={() => setCardItem(it)} className="p-1.5 rounded hover:bg-slate-100 text-slate-500 hover:text-blue-600"><ClipboardList className="w-4 h-4" /></button>
                        )}
                        <button title={t('restMenu.editItem')} onClick={() => setEdit({ item: it })} className="p-1.5 rounded hover:bg-slate-100 text-slate-500 hover:text-blue-600"><Pencil className="w-4 h-4" /></button>
                        <button title={t('restMenu.delete')} onClick={() => remove(it)} className="p-1.5 rounded hover:bg-slate-100 text-slate-500 hover:text-rose-600"><Trash2 className="w-4 h-4" /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {edit && (
        <ItemModal kind={edit.item?.kind || tab} item={edit.item} categories={categories} stations={stations}
                   onClose={() => setEdit(null)} onSaved={afterSave} t={t} />
      )}
      {cardItem && (
        <CardModal item={cardItem} components={components} alertPct={alertPct}
                   onClose={() => setCardItem(null)} onSaved={afterSave} t={t} />
      )}
    </div>
  );
}
