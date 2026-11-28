import { useState, useEffect, useCallback, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Plus, Search, Pencil, Trash2, ClipboardList, X, ListPlus, FileUp, FileDown, FileSpreadsheet } from 'lucide-react';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import useCompanyFeatures from '../../../hooks/useCompanyFeatures';
import { fmtQty } from '../../../utils/qty';
import { loadXLSX, loadSaveAs } from '../../../utils/excelLazy';

// R1: restoran menyusi — taomlar, yarim tayyorlar, ingredientlar, tovarlar, sexlar va texnologik kartalar.
// Backend: app/routers/restaurant_menu.py. Marshrut App.jsx'da FeatureGate feature="restaurant" bilan o'ralgan.

const TABS = [
  { key: 'dish', label: 'restMenu.tabDish' },
  { key: 'semi', label: 'restMenu.tabSemi' },
  { key: 'ingredient', label: 'restMenu.tabIngredient' },
  { key: 'goods', label: 'restMenu.tabGoods' },
  { key: 'modifiers', label: 'restMod.tab' },
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

// ───────────────────────── Qo'shimchalar (R1.3) ─────────────────────────

const emptyMod = () => ({ name: '', price: '', product_id: '', quantity: '', is_active: true });

function GroupModal({ group, components, onClose, onSaved, t }) {
  const [form, setForm] = useState(() => ({
    name: group?.name || '',
    min_select: String(group?.min_select ?? 0),
    max_select: String(group?.max_select ?? 1),
    is_active: group?.is_active ?? true,
  }));
  const [rows, setRows] = useState(() => (group?.modifiers?.length ? group.modifiers.map(m => ({
    id: m.id, name: m.name, price: m.price ? String(m.price) : '', product_id: m.product_id ? String(m.product_id) : '',
    quantity: m.quantity ? String(m.quantity) : '', is_active: m.is_active,
  })) : [emptyMod()]));
  const [saving, setSaving] = useState(false);
  const setRow = (i, patch) => setRows(rs => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const save = async () => {
    const body = {
      name: form.name.trim(), min_select: Number(form.min_select) || 0, max_select: Number(form.max_select) || 1,
      is_active: form.is_active,
      modifiers: rows.filter(r => r.name.trim()).map(r => ({
        id: r.id || null, name: r.name.trim(), price: num(r.price) || 0,
        product_id: r.product_id ? Number(r.product_id) : null,
        quantity: r.product_id ? num(r.quantity) : null, is_active: r.is_active,
      })),
    };
    setSaving(true);
    try {
      if (group) await api.put(`/restaurant/modifier-groups/${group.id}`, body);
      else await api.post('/restaurant/modifier-groups', body);
      toast.success(t('restMenu.saved'));
      onSaved();
    } catch (err) { toast.error(err.response?.data?.detail || t('restMenu.saveFailed')); }
    finally { setSaving(false); }
  };

  return (
    <Modal title={group ? t('restMod.editGroup') : t('restMod.newGroup')} onClose={onClose} wide>
      <div className="grid sm:grid-cols-4 gap-3">
        <div className="sm:col-span-2">
          <Field label={t('restMod.groupName')}>
            <input className={inputCls} value={form.name} maxLength={100} placeholder={t('restMod.groupNamePh')}
                   onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          </Field>
        </div>
        <Field label={t('restMod.minSelect')}>
          <input className={inputCls} type="number" min="0" max="20" value={form.min_select}
                 onChange={e => setForm(f => ({ ...f, min_select: e.target.value }))} />
        </Field>
        <Field label={t('restMod.maxSelect')}>
          <input className={inputCls} type="number" min="1" max="20" value={form.max_select}
                 onChange={e => setForm(f => ({ ...f, max_select: e.target.value }))} />
        </Field>
      </div>
      <p className="text-xs text-slate-500 mt-2">{t('restMod.minHint')}</p>
      <label className="mt-2 flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" checked={form.is_active} onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))} />
        {t('restMenu.active')}
      </label>

      <div className="mt-4 border border-slate-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs text-slate-500">
            <tr>
              <th className="text-left px-3 py-2">{t('restMod.option')}</th>
              <th className="text-right px-3 py-2 w-28">{t('restMod.extraPrice')}</th>
              <th className="text-left px-3 py-2">{t('restMod.linkedProduct')}</th>
              <th className="text-right px-3 py-2 w-24">{t('restMod.qty')}</th>
              <th className="w-16" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const unit = components.find(c => String(c.id) === r.product_id)?.unit || '';
              return (
                <tr key={r.id || `n${i}`} className="border-t border-slate-100">
                  <td className="px-2 py-1.5">
                    <input className={inputCls} value={r.name} maxLength={100} onChange={e => setRow(i, { name: e.target.value })} />
                  </td>
                  <td className="px-2 py-1.5">
                    <input className={`${inputCls} text-right`} inputMode="decimal" value={r.price} placeholder="0"
                           onChange={e => setRow(i, { price: e.target.value })} />
                  </td>
                  <td className="px-2 py-1.5">
                    <select className={inputCls} value={r.product_id} onChange={e => setRow(i, { product_id: e.target.value })}>
                      <option value="">{t('restMod.noLink')}</option>
                      {components.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </td>
                  <td className="px-2 py-1.5">
                    {r.product_id && (
                      <div className="flex items-center gap-1">
                        <input className={`${inputCls} text-right`} inputMode="decimal" value={r.quantity}
                               onChange={e => setRow(i, { quantity: e.target.value })} />
                        <span className="text-[11px] text-slate-400">{unit}</span>
                      </div>
                    )}
                  </td>
                  <td className="px-2 py-1.5">
                    <div className="flex items-center gap-1 justify-end">
                      <input type="checkbox" title={t('restMenu.active')} checked={r.is_active}
                             onChange={e => setRow(i, { is_active: e.target.checked })} />
                      <button className="p-1 text-slate-400 hover:text-rose-600" title={t('restMenu.delete')}
                              onClick={() => setRows(rs => rs.filter((_, j) => j !== i))}><Trash2 className="w-4 h-4" /></button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <button className={`${btnGhost} mt-2`} onClick={() => setRows(rs => [...rs, emptyMod()])}>
        <Plus className="w-4 h-4" />{t('restMod.addOption')}
      </button>
      <p className="text-xs text-slate-500 mt-2">{t('restMod.linkHint')}</p>

      <div className="flex justify-end gap-2 mt-5">
        <button className={btnGhost} onClick={onClose}>{t('restMenu.cancel')}</button>
        <button className={btnPrimary} disabled={saving || !form.name.trim()} onClick={save}>{t('restMenu.save')}</button>
      </div>
    </Modal>
  );
}

function ModifiersPanel({ components, t }) {
  const [groups, setGroups] = useState([]);
  const [edit, setEdit] = useState(null);     // {group|null}
  const load = useCallback(() => {
    api.get('/restaurant/modifier-groups').then(r => setGroups(r.data))
      .catch(err => toast.error(err.response?.data?.detail || t('restMenu.loadFailed')));
  }, [t]);
  useEffect(() => { load(); }, [load]);

  const remove = async g => {
    if (!window.confirm(`${t('restMod.confirmDelete')}: ${g.name}?`)) return;
    try {
      await api.delete(`/restaurant/modifier-groups/${g.id}`);
      toast.success(t('restMenu.deleted'));
      load();
    } catch (err) { toast.error(err.response?.data?.detail || t('restMenu.saveFailed')); }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl">
      <div className="p-3 flex flex-wrap gap-2 items-center border-b border-slate-100">
        <p className="flex-1 min-w-[200px] text-xs text-slate-500">{t('restMod.hint')}</p>
        <button className={btnPrimary} onClick={() => setEdit({ group: null })}><Plus className="w-4 h-4" />{t('restMod.newGroup')}</button>
      </div>
      <div className="divide-y divide-slate-100">
        {groups.length === 0 && <div className="px-4 py-8 text-center text-sm text-slate-400">{t('restMod.empty')}</div>}
        {groups.map(g => (
          <div key={g.id} className={`px-4 py-3 flex items-start gap-3 ${g.is_active ? '' : 'opacity-50'}`}>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-slate-800">
                {g.name}
                <span className="ml-2 text-xs font-normal text-slate-500">
                  {g.required ? t('restMod.required') : t('restMod.optional')}, {t('restMod.upTo')} {g.max_select}
                </span>
              </div>
              <div className="text-xs text-slate-600 mt-0.5">
                {g.modifiers.filter(m => m.is_active).map(m => (m.price ? `${m.name} +${money(m.price)}` : m.name)).join(', ')}
              </div>
              <div className="text-[11px] text-slate-400 mt-0.5">{t('restMod.dishesCount')}: {g.product_ids.length}</div>
            </div>
            <button title={t('restMenu.editItem')} onClick={() => setEdit({ group: g })} className="p-1.5 rounded hover:bg-slate-100 text-slate-500 hover:text-blue-600"><Pencil className="w-4 h-4" /></button>
            <button title={t('restMenu.delete')} onClick={() => remove(g)} className="p-1.5 rounded hover:bg-slate-100 text-slate-500 hover:text-rose-600"><Trash2 className="w-4 h-4" /></button>
          </div>
        ))}
      </div>
      {edit && <GroupModal group={edit.group} components={components} t={t}
                           onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
    </div>
  );
}

function DishModsModal({ item, onClose, onSaved, t }) {
  const [groups, setGroups] = useState(null);
  const [picked, setPicked] = useState(item.modifier_group_ids || []);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    api.get('/restaurant/modifier-groups').then(r => setGroups(r.data)).catch(() => setGroups([]));
  }, []);
  const toggle = id => setPicked(p => (p.includes(id) ? p.filter(x => x !== id) : [...p, id]));
  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/restaurant/menu/items/${item.id}/modifier-groups`, { group_ids: picked });
      toast.success(t('restMenu.saved'));
      onSaved();
    } catch (err) { toast.error(err.response?.data?.detail || t('restMenu.saveFailed')); }
    finally { setSaving(false); }
  };
  return (
    <Modal title={`${t('restMod.dishGroups')}: ${item.name}`} onClose={onClose}>
      {groups === null && <div className="text-sm text-slate-400">{t('restMenu.loading')}</div>}
      {groups && groups.length === 0 && <div className="text-sm text-slate-500">{t('restMod.emptyGoTab')}</div>}
      <div className="space-y-2">
        {(groups || []).map(g => (
          <label key={g.id} className={`flex items-start gap-2 p-2 rounded-lg border cursor-pointer ${picked.includes(g.id) ? 'border-blue-600 bg-blue-50' : 'border-slate-200'} ${g.is_active ? '' : 'opacity-50'}`}>
            <input type="checkbox" className="mt-1" checked={picked.includes(g.id)} onChange={() => toggle(g.id)} />
            <span className="text-sm">
              <span className="font-semibold text-slate-800">{g.name}</span>
              <span className="ml-1 text-xs text-slate-500">({g.required ? t('restMod.required') : t('restMod.optional')})</span>
              <span className="block text-xs text-slate-500">{g.modifiers.filter(m => m.is_active).map(m => m.name).join(', ')}</span>
            </span>
          </label>
        ))}
      </div>
      <div className="flex justify-end gap-2 mt-5">
        <button className={btnGhost} onClick={onClose}>{t('restMenu.cancel')}</button>
        <button className={btnPrimary} disabled={saving || groups === null} onClick={save}>{t('restMenu.save')}</button>
      </div>
    </Modal>
  );
}

// ───────────────────────── Sahifa ─────────────────────────

// ── R1.2: tex kartalar Excel eksport / import (fayl brauzerda o'qiladi va yoziladi) ──
// Ustun nomlari uch tilda ham taniladi; serverga kanonik kalitlar yuboriladi.
const XL_COLS = [
  ['dish', ['taom', 'блюдо', 'dish']],
  ['dish_code', ['taom kodi', 'код блюда', 'dish code']],
  ['kind', ['turi', 'тип', 'type']],
  ['output_qty', ['chiqish', 'выход', 'yield']],
  ['output_weight_g', ["porsiya og'irligi (g)", 'вес порции (г)', 'portion weight (g)']],
  ['cooking_time_min', ['tayyorlash vaqti (daq)', 'время приготовления (мин)', 'cooking time (min)']],
  ['ingredient', ['ingredient', 'ингредиент']],
  ['ingredient_code', ['ingredient kodi', 'код ингредиента', 'ingredient code']],
  ['unit', ['birlik', 'ед. изм.', 'unit']],
  ['gross', ['brutto', 'брутто', 'gross']],
  ['net', ['netto', 'нетто', 'net']],
  ['loss_cold', ["sovuq yo'qotish %", 'потери холодные %', 'cold loss %']],
  ['loss_hot', ["issiq yo'qotish %", 'потери горячие %', 'hot loss %']],
  ['price', ['ingredient narxi', 'цена ингредиента', 'ingredient price']],
];
const XL_EXTRA = ['line_cost', 'sale_price', 'version'];
const XL_HEADER_TO_KEY = Object.fromEntries(XL_COLS.flatMap(([k, names]) => [[k, k], ...names.map(n => [n, k])]));
const xlNorm = s => String(s ?? '').trim().toLowerCase().replace(/\s+/g, ' ').replace(/[‘’`ʻʼ]/g, "'");
const XL_STATUS_CLS = { created: 'text-emerald-700', updated: 'text-blue-700', unchanged: 'text-slate-500', error: 'text-rose-700' };

async function downloadCardsXlsx(t, rows, fileName) {
  const [XLSX, saveAs] = await Promise.all([loadXLSX(), loadSaveAs()]);
  const cols = [...XL_COLS.map(([k]) => k), ...XL_EXTRA];
  const data = rows.map(r => Object.fromEntries(cols.map(k => [t(`restXl.col.${k}`),
    k === 'kind' ? t(`restXl.kind.${r.kind || 'dish'}`) : (r[k] ?? '')])));
  const ws = XLSX.utils.json_to_sheet(data, { header: cols.map(k => t(`restXl.col.${k}`)) });
  ws['!cols'] = cols.map(k => ({ wch: ['dish', 'ingredient'].includes(k) ? 26 : 14 }));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, t('restXl.sheet'));
  saveAs(new Blob([XLSX.write(wb, { type: 'array', bookType: 'xlsx' })]), fileName);
}

function CardsImportModal({ onClose, onDone, t }) {
  const [rows, setRows] = useState(null);
  const [fileName, setFileName] = useState('');
  const [unknown, setUnknown] = useState([]);
  const [createMissing, setCreateMissing] = useState(false);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const readFile = async file => {
    if (!file) return;
    setResult(null);
    setFileName(file.name);
    try {
      const XLSX = await loadXLSX();
      const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' });
      const ws = wb.Sheets[wb.SheetNames[0]];
      const raw = XLSX.utils.sheet_to_json(ws, { defval: '', raw: false });
      const unk = new Set();
      const mapped = raw.map((r, i) => {
        const o = { row: i + 2 };
        Object.entries(r).forEach(([h, v]) => {
          const k = XL_HEADER_TO_KEY[xlNorm(h)];
          if (k) o[k] = v;
          else if (!XL_EXTRA.some(x => xlNorm(t(`restXl.col.${x}`)) === xlNorm(h))) unk.add(h);
        });
        return o;
      }).filter(o => String(o.dish || '').trim() || String(o.ingredient || '').trim());
      setUnknown([...unk]);
      setRows(mapped);
      if (!mapped.length) toast.error(t('restXl.emptyFile'));
    } catch {
      toast.error(t('restXl.readFailed'));
      setRows(null);
    }
  };

  const send = async dryRun => {
    setBusy(true);
    try {
      const r = await api.post('/restaurant/menu/cards/import', { rows, create_missing: createMissing, dry_run: dryRun });
      setResult(r.data);
      if (!dryRun) {
        toast.success(t('restXl.imported', { n: r.data.summary.created + r.data.summary.updated }));
        onDone();
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || t('restMenu.saveFailed'));
    }
    setBusy(false);
  };

  const s = result?.summary;
  const canApply = result && !result.applied && (s.created + s.updated > 0);
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-start justify-center overflow-y-auto p-4" onMouseDown={onClose}>
      <div className="bg-white rounded-xl border border-slate-200 w-full max-w-3xl mt-10" onMouseDown={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
          <h3 className="text-base font-bold text-slate-800">{t('restXl.importTitle')}</h3>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-3">
          <p className="text-xs text-slate-500">{t('restXl.importHint')}</p>
          <div className="flex flex-wrap items-center gap-2">
            <label className={`${btnGhost} cursor-pointer`}>
              <FileUp className="w-4 h-4" />{t('restXl.chooseFile')}
              <input type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={e => { readFile(e.target.files?.[0]); e.target.value = ''; }} />
            </label>
            {fileName && <span className="text-sm text-slate-600">{fileName}{rows ? `: ${t('restXl.rowsN', { n: rows.length })}` : ''}</span>}
          </div>
          {unknown.length > 0 && <p className="text-xs text-amber-800">{t('restXl.unknownCols')}: {unknown.join(', ')}</p>}
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={createMissing} onChange={e => { setCreateMissing(e.target.checked); setResult(null); }} />
            {t('restXl.createMissing')}
          </label>

          {result && (
            <div className="space-y-2">
              <div className="flex flex-wrap gap-3 text-sm">
                {['created', 'updated', 'unchanged', 'error'].map(k => (
                  <span key={k} className={XL_STATUS_CLS[k]}>{t(`restXl.st.${k}`)}: <b>{s[k]}</b></span>
                ))}
                {result.applied && <span className="text-emerald-700 font-semibold">{t('restXl.applied')}</span>}
                {!result.applied && <span className="text-slate-500">{t('restXl.preview')}</span>}
              </div>
              {(result.created_dishes.length > 0 || result.created_ingredients.length > 0) && (
                <p className="text-xs text-slate-600">
                  {t('restXl.willCreate')}: {[...result.created_dishes, ...result.created_ingredients].join(', ')}
                </p>
              )}
              <div className="border border-slate-200 rounded-lg max-h-64 overflow-y-auto">
                <table className="w-full text-sm">
                  <tbody className="divide-y divide-slate-100">
                    {result.cards.map((c, i) => (
                      <tr key={i}>
                        <td className="px-3 py-1.5 text-slate-800">{c.name}{c.kind === 'semi' ? <span className="ml-1 text-xs text-slate-500">({t('restXl.kind.semi')})</span> : null}</td>
                        <td className="px-3 py-1.5 text-xs text-slate-500">{t('restXl.rowsN', { n: c.rows })}</td>
                        <td className={`px-3 py-1.5 text-xs ${XL_STATUS_CLS[c.status]}`}>
                          {t(`restXl.st.${c.status}`)}{c.version ? ` v${c.version}` : ''}{c.error ? `: ${c.error}` : ''}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {result.row_errors.length > 0 && (
                <div className="border border-rose-200 bg-rose-50 rounded-lg px-3 py-2 max-h-40 overflow-y-auto text-xs text-rose-800 space-y-0.5">
                  {result.row_errors.map((e, i) => <div key={i}>{t('restXl.row')} {e.row}: {e.message}</div>)}
                </div>
              )}
            </div>
          )}

          <div className="flex flex-wrap justify-end gap-2 pt-1">
            <button className={btnGhost} onClick={onClose}>{t('restXl.close')}</button>
            <button className={btnGhost} disabled={busy || !rows?.length} onClick={() => send(true)}>{t('restXl.check')}</button>
            <button className={btnPrimary} disabled={busy || !canApply} onClick={() => send(false)}>{t('restXl.apply')}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

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
  const [xlImport, setXlImport] = useState(false);
  const [loading, setLoading] = useState(false);
  const [edit, setEdit] = useState(null);      // {item|null}
  const [cardItem, setCardItem] = useState(null);
  const [modsItem, setModsItem] = useState(null);

  const loadRefs = useCallback(() => {
    api.get('/restaurant/menu/categories').then(r => setCategories(r.data)).catch(() => {});
    api.get('/restaurant/stations').then(r => setStations(r.data)).catch(() => {});
  }, []);

  const loadItems = useCallback(() => {
    if (tab === 'stations' || tab === 'modifiers') return;
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

  const exportCards = async () => {
    try {
      const r = await api.get('/restaurant/menu/cards/export');
      if (!r.data.rows.length) { toast(t('restXl.nothingToExport')); return; }
      await downloadCardsXlsx(t, r.data.rows, `tex_kartalar_${new Date().toISOString().slice(0, 10)}.xlsx`);
    } catch (err) { toast.error(err.response?.data?.detail || t('restMenu.saveFailed')); }
  };
  const downloadTemplate = () => downloadCardsXlsx(t, [
    { dish: 'Osh', kind: 'dish', output_qty: 1, output_weight_g: 350, cooking_time_min: 40, ingredient: 'Guruch', unit: 'kg', gross: 0.15, net: 0.15 },
    { dish: 'Osh', kind: 'dish', ingredient: "Mol go'shti", unit: 'kg', gross: 0.12, net: 0.1, loss_cold: 15, price: 110000 },
    { dish: 'Qiyma', kind: 'semi', output_qty: 5, ingredient: "Mol go'shti", unit: 'kg', gross: 4.5, net: 4.2 },
  ], 'tex_karta_shablon.xlsx');

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

      {tab === 'modifiers' && <ModifiersPanel components={components} t={t} />}
      {tab === 'stations' ? (
        <StationsPanel stations={stations} categories={categories} reload={loadRefs} t={t} />
      ) : tab === 'modifiers' ? null : (
        <div className="bg-white border border-slate-200 rounded-xl">
          <div className="p-3 flex flex-wrap gap-2 items-center border-b border-slate-100">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input className={`${inputCls} pl-9`} value={q} onChange={e => setQ(e.target.value)} placeholder={t('restMenu.search')} />
            </div>
            <button className={btnPrimary} onClick={() => setEdit({ item: null })}><Plus className="w-4 h-4" />{t(`restMenu.add.${tab}`)}</button>
            {HAS_CARD.includes(tab) && (
              <>
                <button className={btnGhost} onClick={exportCards}><FileDown className="w-4 h-4" />{t('restXl.export')}</button>
                <button className={btnGhost} onClick={() => setXlImport(true)}><FileUp className="w-4 h-4" />{t('restXl.import')}</button>
                <button className={btnGhost} onClick={downloadTemplate} title={t('restXl.templateHint')}><FileSpreadsheet className="w-4 h-4" />{t('restXl.template')}</button>
              </>
            )}
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
                        {it.kind === 'dish' && it.modifier_group_ids?.length > 0 && (
                          <span className="ml-2">{t('restMod.tab')}: {it.modifier_group_ids.length}</span>
                        )}
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
                        {it.kind === 'dish' && (
                          <button title={t('restMod.dishGroups')} onClick={() => setModsItem(it)} className="p-1.5 rounded hover:bg-slate-100 text-slate-500 hover:text-blue-600"><ListPlus className="w-4 h-4" /></button>
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
      {modsItem && (
        <DishModsModal item={modsItem} onClose={() => setModsItem(null)} t={t}
                       onSaved={() => { setModsItem(null); loadItems(); }} />
      )}
      {xlImport && <CardsImportModal t={t} onClose={() => setXlImport(false)} onDone={() => { loadItems(); loadComponents(); }} />}
      {cardItem && (
        <CardModal item={cardItem} components={components} alertPct={alertPct}
                   onClose={() => setCardItem(null)} onSaved={afterSave} t={t} />
      )}
    </div>
  );
}
