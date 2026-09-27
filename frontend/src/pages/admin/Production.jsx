import { useState, useEffect, useCallback } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import { Card, StatCard } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/ui/DataTable';

const fmt = (n) => Number(n ?? 0).toLocaleString('uz-UZ');
const fmtDate = (s) => s ? new Date(s).toLocaleString('uz-UZ') : '—';

const STATUS_COLOR = { draft: 'neutral', in_progress: 'warning', completed: 'success', cancelled: 'danger' };
const COST_TYPES = ['labor', 'utility', 'overhead', 'other'];

// ─── BOM (RETSEPTURALAR) TAB ────────────────────────────────────────────────
function BomsTab({ products }) {
  const { t } = useLang();
  const [boms, setBoms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null); // { mode: 'create' } | { mode: 'edit', bom }
  const [form, setForm] = useState({ product_id: '', name: '', items: [{ component_product_id: '', quantity_per_unit: '' }] });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/production/boms');
      setBoms(data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setForm({ product_id: '', name: '', items: [{ component_product_id: '', quantity_per_unit: '' }] });
    setErr(''); setModal({ mode: 'create' });
  };
  const openEdit = async (bomListItem) => {
    const { data } = await api.get(`/production/boms/${bomListItem.id}`);
    setForm({
      product_id: String(data.product_id),
      name: data.name,
      items: data.items.map(i => ({ component_product_id: String(i.component_product_id), quantity_per_unit: String(i.quantity_per_unit) })),
    });
    setErr(''); setModal({ mode: 'edit', bom: data });
  };

  const addItem = () => setForm(f => ({ ...f, items: [...f.items, { component_product_id: '', quantity_per_unit: '' }] }));
  const removeItem = (idx) => setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) }));
  const setItem = (idx, key, val) => setForm(f => {
    const items = [...f.items];
    items[idx] = { ...items[idx], [key]: val };
    return { ...f, items };
  });

  const save = async () => {
    if (!form.product_id || !form.name.trim()) { setErr(t('common.error')); return; }
    const validItems = form.items.filter(i => i.component_product_id && Number(i.quantity_per_unit) > 0);
    if (!validItems.length) { setErr(t('production.selectComponentsError')); return; }
    setSaving(true); setErr('');
    try {
      const payload = {
        product_id: Number(form.product_id),
        name: form.name.trim(),
        items: validItems.map(i => ({ component_product_id: Number(i.component_product_id), quantity_per_unit: Number(i.quantity_per_unit) })),
      };
      if (modal.mode === 'create') await api.post('/production/boms', payload);
      else await api.put(`/production/boms/${modal.bom.id}`, payload);
      setModal(null); load();
    } catch (e) { setErr(e.response?.data?.detail || t('common.error')); }
    finally { setSaving(false); }
  };

  const remove = async (bom) => {
    if (!window.confirm(t('production.confirmDeleteBom'))) return;
    try { await api.delete(`/production/boms/${bom.id}`); load(); }
    catch (e) { alert(e.response?.data?.detail || t('common.error')); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <button onClick={openCreate}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand text-white text-sm font-semibold rounded-xl hover:bg-brand-deep transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {t('production.newBom')}
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-7 h-7 border-4 border-brand border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <DataTable
          emptyText={t('production.noBoms')}
          columns={[
            { key: 'name', label: t('production.bomName') },
            { key: 'product_name', label: t('production.finishedProduct') },
            { key: 'item_count', label: t('production.itemsCount'), align: 'center' },
            { key: 'status', label: t('common.type') || 'Status', align: 'center', render: (b) => <Badge color={b.is_active ? 'success' : 'neutral'}>{b.is_active ? t('production.active') : t('production.inactive')}</Badge> },
            { key: 'actions', label: '', align: 'right', render: (b) => (
              <div className="flex items-center justify-end gap-1.5">
                <button onClick={() => openEdit(b)} className="p-1.5 bg-brand/10 text-brand hover:bg-brand/20 rounded-lg transition-colors">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536M9 13l6.5-6.5a2 2 0 012.828 0l.172.172a2 2 0 010 2.828L12 16H9v-3z" /></svg>
                </button>
                <button onClick={() => remove(b)} className="p-1.5 bg-danger/10 text-danger hover:bg-danger/20 rounded-lg transition-colors">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
              </div>
            ) },
          ]}
          rows={boms}
        />
      )}

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-surface rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-line">
              <h3 className="text-base font-bold text-ink-900">{modal.mode === 'create' ? t('production.newBom') : t('common.edit')}</h3>
              <button onClick={() => setModal(null)} className="text-ink-300 hover:text-ink-500">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="px-6 py-5 space-y-4 overflow-y-auto flex-1">
              <div>
                <label className="block text-xs font-semibold text-ink-500 mb-1">{t('production.bomName')} *</label>
                <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  className="w-full px-3 py-2.5 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-ink-500 mb-1">{t('production.finishedProduct')} *</label>
                <select value={form.product_id} disabled={modal.mode === 'edit'} onChange={e => setForm(f => ({ ...f, product_id: e.target.value }))}
                  className="w-full px-3 py-2.5 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40 disabled:bg-surface-sunken disabled:text-ink-300">
                  <option value="">{t('ombor.selectProductEllipsis')}</option>
                  {products.filter(p => p.product_type !== 'raw_material').map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-ink-500 uppercase tracking-wider">{t('production.components')}</label>
                  <button onClick={addItem} className="text-xs text-brand font-semibold hover:text-brand-deep">{t('production.addComponent')}</button>
                </div>
                {form.items.map((it, idx) => (
                  <div key={idx} className="flex gap-2 items-center">
                    <select value={it.component_product_id} onChange={e => setItem(idx, 'component_product_id', e.target.value)}
                      className="flex-1 px-3 py-2 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40">
                      <option value="">{t('production.componentProduct')}</option>
                      {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                    <input type="number" min="0" step="any" value={it.quantity_per_unit} onChange={e => setItem(idx, 'quantity_per_unit', e.target.value)}
                      placeholder={t('production.qtyPerUnit')}
                      className="w-32 px-3 py-2 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40" />
                    {form.items.length > 1 && (
                      <button onClick={() => removeItem(idx)} className="text-danger/70 hover:text-danger">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                      </button>
                    )}
                  </div>
                ))}
              </div>
              {err && <p className="text-sm text-danger font-medium">{err}</p>}
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-line">
              <button onClick={() => setModal(null)} className="px-4 py-2 text-sm font-medium text-ink-500 border border-line rounded-xl hover:bg-surface-sunken transition-colors">{t('common.cancel')}</button>
              <button onClick={save} disabled={saving} className="px-5 py-2 bg-brand text-white text-sm font-semibold rounded-xl hover:bg-brand-deep disabled:opacity-60 transition-colors">
                {saving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── ISHLAB CHIQARISH BUYURTMALARI TAB ──────────────────────────────────────
function OrdersTab({ warehouses }) {
  const { t } = useLang();
  const [orders, setOrders] = useState([]);
  const [boms, setBoms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState(null);
  const [createForm, setCreateForm] = useState({ bom_id: '', planned_quantity: '', warehouse_id: '', target_warehouse_id: '', note: '' });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ord, bm] = await Promise.all([
        api.get('/production/orders'),
        api.get('/production/boms', { params: { is_active: true } }),
      ]);
      setOrders(ord.data);
      setBoms(bm.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openDetail = async (row) => {
    const { data } = await api.get(`/production/orders/${row.id}`);
    setDetail(data);
  };

  const createOrder = async () => {
    if (!createForm.bom_id || !createForm.planned_quantity || !createForm.warehouse_id || !createForm.target_warehouse_id) {
      setErr(t('common.error')); return;
    }
    if (createForm.warehouse_id === createForm.target_warehouse_id) { setErr(t('production.sameWarehouseError')); return; }
    setSaving(true); setErr('');
    try {
      const { data } = await api.post('/production/orders', {
        bom_id: Number(createForm.bom_id),
        planned_quantity: Number(createForm.planned_quantity),
        warehouse_id: Number(createForm.warehouse_id),
        target_warehouse_id: Number(createForm.target_warehouse_id),
        note: createForm.note || null,
      });
      setShowCreate(false);
      setCreateForm({ bom_id: '', planned_quantity: '', warehouse_id: '', target_warehouse_id: '', note: '' });
      load();
      setDetail(data);
    } catch (e) { setErr(e.response?.data?.detail || t('common.error')); }
    finally { setSaving(false); }
  };

  const start = async (order) => {
    try { const { data } = await api.post(`/production/orders/${order.id}/start`); setDetail(data); load(); }
    catch (e) { alert(e.response?.data?.detail || t('common.error')); }
  };
  const cancel = async (order) => {
    if (!window.confirm(t('production.confirmCancel'))) return;
    try { const { data } = await api.post(`/production/orders/${order.id}/cancel`); setDetail(data); load(); }
    catch (e) { alert(e.response?.data?.detail || t('common.error')); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <button onClick={() => { setErr(''); setShowCreate(true); }}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand text-white text-sm font-semibold rounded-xl hover:bg-brand-deep transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
          {t('production.newOrder')}
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-7 h-7 border-4 border-brand border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <DataTable
          emptyText={t('production.noOrders')}
          onRowClick={openDetail}
          columns={[
            { key: 'number', label: t('production.orderNumber') },
            { key: 'product_name', label: t('production.finishedProduct') },
            { key: 'planned_quantity', label: t('production.plannedQty'), align: 'right', numeric: true, render: (o) => fmt(o.planned_quantity) },
            { key: 'produced_quantity', label: t('production.producedQty'), align: 'right', numeric: true, render: (o) => fmt(o.produced_quantity) },
            { key: 'status', label: t('common.type') || 'Status', align: 'center', render: (o) => <Badge color={STATUS_COLOR[o.status]}>{t(`production.status${o.status.charAt(0).toUpperCase() + o.status.slice(1).replace(/_([a-z])/g, (m, c) => c.toUpperCase())}`)}</Badge> },
            { key: 'created_at', label: t('ombor.created') || 'Sana', render: (o) => fmtDate(o.created_at) },
          ]}
          rows={orders}
        />
      )}

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-surface rounded-2xl shadow-2xl w-full max-w-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-line">
              <h3 className="text-base font-bold text-ink-900">{t('production.newOrder')}</h3>
              <button onClick={() => setShowCreate(false)} className="text-ink-300 hover:text-ink-500">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-ink-500 mb-1">{t('production.selectBom')} *</label>
                <select value={createForm.bom_id} onChange={e => setCreateForm(f => ({ ...f, bom_id: e.target.value }))}
                  className="w-full px-3 py-2.5 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40">
                  <option value="">{t('admin.dict.select') || 'Tanlang...'}</option>
                  {boms.map(b => <option key={b.id} value={b.id}>{b.name} ({b.product_name})</option>)}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-ink-500 mb-1">{t('production.plannedQty')} *</label>
                  <input type="number" min="0" step="any" value={createForm.planned_quantity}
                    onChange={e => setCreateForm(f => ({ ...f, planned_quantity: e.target.value }))}
                    className="w-full px-3 py-2.5 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-ink-500 mb-1">{t('production.sourceWarehouse')} *</label>
                  <select value={createForm.warehouse_id} onChange={e => setCreateForm(f => ({ ...f, warehouse_id: e.target.value }))}
                    className="w-full px-3 py-2.5 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40">
                    <option value="">{t('admin.dict.select') || 'Tanlang...'}</option>
                    {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-ink-500 mb-1">{t('production.targetWarehouse')} *</label>
                  <select value={createForm.target_warehouse_id} onChange={e => setCreateForm(f => ({ ...f, target_warehouse_id: e.target.value }))}
                    className="w-full px-3 py-2.5 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40">
                    <option value="">{t('admin.dict.select') || 'Tanlang...'}</option>
                    {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-ink-500 mb-1">{t('production.noteOptional')}</label>
                <input value={createForm.note} onChange={e => setCreateForm(f => ({ ...f, note: e.target.value }))}
                  className="w-full px-3 py-2.5 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40" />
              </div>
              {err && <p className="text-sm text-danger font-medium">{err}</p>}
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-line">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm font-medium text-ink-500 border border-line rounded-xl hover:bg-surface-sunken transition-colors">{t('common.cancel')}</button>
              <button onClick={createOrder} disabled={saving} className="px-5 py-2 bg-brand text-white text-sm font-semibold rounded-xl hover:bg-brand-deep disabled:opacity-60 transition-colors">
                {saving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Detail / complete modal */}
      {detail && (
        <OrderDetailModal order={detail} onClose={() => setDetail(null)} onStart={start} onCancel={cancel}
          onCompleted={(updated) => { setDetail(updated); load(); }} />
      )}
    </div>
  );
}

function OrderDetailModal({ order, onClose, onStart, onCancel, onCompleted }) {
  const { t } = useLang();
  const [producedQty, setProducedQty] = useState(String(order.planned_quantity));
  const [defectQty, setDefectQty] = useState('0');
  const [costs, setCosts] = useState([{ cost_type: 'labor', amount: '', note: '' }]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const addCost = () => setCosts(c => [...c, { cost_type: 'labor', amount: '', note: '' }]);
  const removeCost = (idx) => setCosts(c => c.filter((_, i) => i !== idx));
  const setCost = (idx, key, val) => setCosts(c => { const arr = [...c]; arr[idx] = { ...arr[idx], [key]: val }; return arr; });

  const complete = async () => {
    if (!producedQty || Number(producedQty) <= 0) { setErr(t('common.error')); return; }
    setSaving(true); setErr('');
    try {
      const { data } = await api.post(`/production/orders/${order.id}/complete`, {
        produced_quantity: Number(producedQty),
        defect_quantity: Number(defectQty || 0),
        costs: costs.filter(c => Number(c.amount) > 0).map(c => ({ cost_type: c.cost_type, amount: Number(c.amount), note: c.note || null })),
      });
      onCompleted(data);
    } catch (e) { setErr(e.response?.data?.detail || t('common.error')); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-surface rounded-2xl shadow-2xl w-full max-w-xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-line">
          <div>
            <h3 className="text-base font-bold text-ink-900 font-mono">{order.number}</h3>
            <p className="text-xs text-ink-500">{order.product_name} — {order.bom_name}</p>
          </div>
          <button onClick={onClose} className="text-ink-300 hover:text-ink-500">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="px-6 py-5 space-y-4 overflow-y-auto flex-1">
          <div className="flex items-center gap-3 flex-wrap">
            <Badge color={STATUS_COLOR[order.status]}>{t(`production.status${order.status.charAt(0).toUpperCase() + order.status.slice(1).replace(/_([a-z])/g, (m, c) => c.toUpperCase())}`)}</Badge>
            <span className="text-sm text-ink-500">{order.warehouse_name} → {order.target_warehouse_name}</span>
          </div>

          {order.shortages?.length > 0 && (
            <Card className="bg-danger/5 border-danger/30 !p-3">
              <p className="text-sm font-semibold text-danger mb-1">{t('production.shortageWarning')}</p>
              {order.shortages.map((s, i) => (
                <p key={i} className="text-xs text-danger/80">{s.component_product_name}: {t('production.shortageDetail')} {fmt(s.required_quantity)} / {fmt(s.available_quantity)}</p>
              ))}
            </Card>
          )}

          {order.status === 'completed' && (
            <div className="grid grid-cols-2 gap-3">
              <Card className="!p-3"><div className="text-[10px] uppercase text-ink-300 font-semibold">{t('production.unitCost')}</div><div className="text-lg font-bold text-ink-900 tabular-nums">{fmt(order.unit_cost)}</div></Card>
              <Card className="!p-3"><div className="text-[10px] uppercase text-ink-300 font-semibold">{t('production.totalCost')}</div><div className="text-lg font-bold text-ink-900 tabular-nums">{fmt(order.total_cost)}</div></Card>
            </div>
          )}

          {order.status === 'in_progress' && (
            <div className="space-y-4 border-t border-line pt-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-ink-500 mb-1">{t('production.producedQty')} *</label>
                  <input type="number" min="0" step="any" value={producedQty} onChange={e => setProducedQty(e.target.value)}
                    className="w-full px-3 py-2.5 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-ink-500 mb-1">{t('production.defectQty')}</label>
                  <input type="number" min="0" step="any" value={defectQty} onChange={e => setDefectQty(e.target.value)}
                    className="w-full px-3 py-2.5 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40" />
                </div>
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-ink-500 uppercase tracking-wider">{t('production.costs')}</label>
                  <button onClick={addCost} className="text-xs text-brand font-semibold hover:text-brand-deep">{t('production.addCost')}</button>
                </div>
                {costs.map((c, idx) => (
                  <div key={idx} className="flex gap-2 items-center">
                    <select value={c.cost_type} onChange={e => setCost(idx, 'cost_type', e.target.value)}
                      className="w-36 px-2.5 py-2 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40">
                      {COST_TYPES.map(ct => <option key={ct} value={ct}>{t(`production.cost${ct.charAt(0).toUpperCase() + ct.slice(1)}`)}</option>)}
                    </select>
                    <input type="number" min="0" step="any" value={c.amount} onChange={e => setCost(idx, 'amount', e.target.value)}
                      placeholder={t('production.costAmount')}
                      className="w-28 px-2.5 py-2 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40" />
                    <input value={c.note} onChange={e => setCost(idx, 'note', e.target.value)}
                      placeholder={t('production.noteOptional')}
                      className="flex-1 px-2.5 py-2 border border-line rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand/40" />
                    {costs.length > 1 && (
                      <button onClick={() => removeCost(idx)} className="text-danger/70 hover:text-danger">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {err && <p className="text-sm text-danger font-medium">{err}</p>}
        </div>
        <div className="flex items-center justify-between gap-3 px-6 py-4 border-t border-line">
          <div>
            {(order.status === 'draft' || order.status === 'in_progress') && (
              <button onClick={() => onCancel(order)} className="px-4 py-2 text-sm font-semibold text-danger border border-danger/30 rounded-xl hover:bg-danger/5 transition-colors">
                {t('production.cancel')}
              </button>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-ink-500 border border-line rounded-xl hover:bg-surface-sunken transition-colors">{t('common.close') || t('common.cancel')}</button>
            {order.status === 'draft' && (
              <button onClick={() => onStart(order)} className="px-5 py-2 bg-brand text-white text-sm font-semibold rounded-xl hover:bg-brand-deep transition-colors">{t('production.start')}</button>
            )}
            {order.status === 'in_progress' && (
              <button onClick={complete} disabled={saving} className="px-5 py-2 bg-success text-white text-sm font-semibold rounded-xl hover:opacity-90 disabled:opacity-60 transition-colors">
                {saving ? t('common.saving') : t('production.complete')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── MAIN PAGE ───────────────────────────────────────────────────────────────
// ─── Hisobot: davr bo'yicha tannarx va xom ashyo sarfi ─────────────────────
const isoDay = (d) => d.toLocaleDateString('sv-SE');

function ReportTab() {
  const { t } = useLang();
  const [range, setRange] = useState(() => {
    const to = new Date();
    const from = new Date(); from.setDate(from.getDate() - 29);
    return { from: isoDay(from), to: isoDay(to) };
  });
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get('/production/reports', { params: { date_from: range.from, date_to: range.to } })
      .then(r => setData(r.data)).catch(() => setData(null));
  }, [range]);

  const s = data?.summary;
  const costLabel = (ct) => t(`production.cost${ct.charAt(0).toUpperCase() + ct.slice(1)}`);
  const inputCls = 'px-3 py-2 border border-line rounded-xl text-sm bg-surface focus:outline-none focus:ring-2 focus:ring-brand/40';

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 flex-wrap">
        <input type="date" value={range.from} max={range.to} onChange={e => setRange(r => ({ ...r, from: e.target.value }))} className={inputCls} />
        <span className="text-ink-300">—</span>
        <input type="date" value={range.to} min={range.from} onChange={e => setRange(r => ({ ...r, to: e.target.value }))} className={inputCls} />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label={t('production.rpOrders')} value={s ? s.orders : '…'} />
        <StatCard label={t('production.producedQty')} value={s ? fmt(s.produced) : '…'} color="success" />
        <StatCard label={t('production.totalCost')} value={s ? fmt(Math.round(s.total_cost)) : '…'} color="warning" />
        <StatCard label={t('production.rpDefect')} value={s ? fmt(s.defect) : '…'} color="danger" />
      </div>

      {s && s.total_cost > 0 && (
        <Card>
          <div className="text-xs font-semibold text-ink-500 uppercase tracking-wider mb-3">{t('production.rpCostStructure')}</div>
          <div className="flex h-3 rounded-full overflow-hidden bg-surface-sunken">
            <div className="bg-brand" style={{ width: `${(s.raw_material_cost / s.total_cost) * 100}%` }} />
            <div className="bg-warning" style={{ width: `${(s.extra_cost / s.total_cost) * 100}%` }} />
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1 mt-3 text-sm">
            <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-brand" />{t('production.rpRawCost')}: <b className="tabular-nums">{fmt(Math.round(s.raw_material_cost))}</b></span>
            {Object.entries(data.extra_by_type).map(([ct, amt]) => (
              <span key={ct} className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-warning" />{costLabel(ct)}: <b className="tabular-nums">{fmt(Math.round(amt))}</b></span>
            ))}
          </div>
        </Card>
      )}

      <div>
        <h3 className="text-sm font-semibold text-ink-900 mb-2">{t('production.rpByProduct')}</h3>
        <DataTable
          rowKey={r => r.product_id}
          emptyText={data ? t('production.rpEmpty') : '…'}
          rows={data?.products || []}
          columns={[
            { key: 'product_name', label: t('production.finishedProduct') },
            { key: 'orders', label: t('production.rpOrders'), align: 'right', numeric: true },
            { key: 'produced', label: t('production.producedQty'), align: 'right', numeric: true, render: r => `${fmt(r.produced)} ${r.unit || ''}` },
            { key: 'defect_rate', label: t('production.rpDefectRate'), align: 'right', numeric: true, render: r => r.defect ? `${fmt(r.defect)} (${r.defect_rate}%)` : '—' },
            { key: 'avg_unit_cost', label: t('production.unitCost'), align: 'right', numeric: true, render: r => fmt(Math.round(r.avg_unit_cost)) },
            { key: 'total_cost', label: t('production.totalCost'), align: 'right', numeric: true, render: r => fmt(Math.round(r.total_cost)) },
          ]}
        />
      </div>

      <div>
        <h3 className="text-sm font-semibold text-ink-900 mb-2">{t('production.rpConsumption')}</h3>
        <DataTable
          rowKey={r => r.product_id}
          emptyText={data ? t('production.rpEmpty') : '…'}
          rows={data?.consumption || []}
          columns={[
            { key: 'product_name', label: t('production.componentProduct') },
            { key: 'quantity', label: t('production.rpConsumed'), align: 'right', numeric: true, render: r => `${fmt(r.quantity)} ${r.unit || ''}` },
            { key: 'estimated_value', label: t('production.rpEstValue'), align: 'right', numeric: true, render: r => fmt(Math.round(r.estimated_value)) },
          ]}
        />
        <p className="text-[11px] text-ink-300 mt-1.5">{t('production.rpEstHint')}</p>
      </div>
    </div>
  );
}

export default function Production() {
  const { t } = useLang();
  const [activeTab, setActiveTab] = useState('boms');
  const [products, setProducts] = useState([]);
  const [warehouses, setWarehouses] = useState([]);

  useEffect(() => {
    api.get('/products/', { params: { limit: 1000 } }).then(r => setProducts(Array.isArray(r.data) ? r.data : (r.data.items || []))).catch(() => {});
    api.get('/warehouses').then(r => setWarehouses(r.data)).catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-2xl bg-brand flex items-center justify-center shadow-lg shadow-brand/20">
          <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
          </svg>
        </div>
        <div>
          <h2 className="text-lg font-bold text-ink-900">{t('production.title')}</h2>
          <p className="text-sm text-ink-500">{t('production.subtitle')}</p>
        </div>
      </div>

      <div className="flex bg-surface border border-line rounded-xl overflow-hidden shadow-sm w-fit">
        {[['boms', t('production.tabBoms')], ['orders', t('production.tabOrders')], ['report', t('production.tabReport')]].map(([v, l]) => (
          <button key={v} onClick={() => setActiveTab(v)}
            className={`px-5 py-2.5 text-sm font-semibold transition-all ${activeTab === v ? 'bg-brand text-white' : 'text-ink-500 hover:bg-surface-sunken'}`}>
            {l}
          </button>
        ))}
      </div>

      {activeTab === 'boms' && <BomsTab products={products} />}
      {activeTab === 'orders' && <OrdersTab warehouses={warehouses} />}
      {activeTab === 'report' && <ReportTab />}
    </div>
  );
}
