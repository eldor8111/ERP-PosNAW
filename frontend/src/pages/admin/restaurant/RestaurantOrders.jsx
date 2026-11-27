import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import toast from 'react-hot-toast';
import { Plus, Minus, Search, X, Send, Printer, Lock, Unlock, Percent, ArrowRightLeft, Merge, Ban, KeyRound, ShoppingBag, Wallet, Trash2 } from 'lucide-react';
import { fiscalizeAndPrint, registerReturn } from '../../../api/hippoLocal';
import api from '../../../api/axios';
import { useLang } from '../../../context/LangContext';
import { useBranch } from '../../../context/BranchContext';

// R3: ofitsiant va kassa ekrani — zal sxemasida stol holatlari, chek, oshxonaga yuborish, pre-chek, chegirma,
// bekor qilish (menejer PIN tasdig'i), ko'chirish, birlashtirish. Backend: app/routers/restaurant_orders.py.
// To'lov R5 da (kassa). Chek boshqa qurilmada o'zgarsa server 409 ORDER_CHANGED qaytaradi — chek qayta yuklanadi.

const CELL = 24;
const REASONS = ['guest_refused', 'mistake', 'spoiled', 'long_wait', 'other'];
const PAY_TYPES = ['cash', 'card', 'uzcard', 'humo', 'click', 'payme', 'uzum'];
const num = v => Number(String(v ?? '').replace(/\s/g, '').replace(',', '.')) || 0;

// R5: mahalliy fiskal modul (PosKassa bilan bir xil sozlama: fiskalSend + fiskalId)
function fiscalFactoryId() {
  try {
    if (!JSON.parse(localStorage.getItem('fiskalSend') || 'false')) return null;
    return JSON.parse(localStorage.getItem('fiskalId') || 'null');
  } catch { return null; }
}

async function sendFiscal(fiscal, t) {
  const factoryId = fiscalFactoryId();
  if (!factoryId || !fiscal?.cart?.length) return;
  try {
    const { fiscal: res } = await fiscalizeAndPrint({ factoryId, cart: fiscal.cart, payments: fiscal.payments, discountAmount: 0 });
    const sign = res?.fiscal_sign ?? res?.FiscalSign;
    if (fiscal.sale_id && sign) {
      const seq = Number(res?.receipt_seq ?? res?.receipt_number ?? res?.ReceiptSeq);
      const txId = res?.transaction_id ?? res?.TransactionID;
      await api.patch(`/sales/${fiscal.sale_id}/fiscal`, {
        fiscal_sign: String(sign),
        fiscal_qr_url: res?.qr_code_url ?? res?.QRCodeURL ?? undefined,
        fiscal_receipt_seq: Number.isFinite(seq) && seq >= 0 ? seq : undefined,
        fiscal_transaction_id: txId != null ? String(txId) : undefined,
        fiscal_at: new Date().toISOString().slice(0, 19),
        fiscal_factory_id: factoryId,
      }, { _suppressToast: true }).catch(() => toast.error(t('restOrd.fiscalSaveFailed')));
    }
    toast.success(t('restOrd.fiscalSent'));
  } catch (err) {
    toast.error(`${t('restOrd.fiscalFailed')}: ${err?.message || ''}`);
  }
}

// -- to'lov oynasi --
function PayModal({ order, onClose, onPay, busy, t }) {
  const [rows, setRows] = useState([{ type: 'cash', amount: String(Math.round(order.total)) }]);
  const [tips, setTips] = useState('');
  const received = rows.reduce((s, r) => s + num(r.amount), 0);
  const cash = rows.filter(r => r.type === 'cash').reduce((s, r) => s + num(r.amount), 0);
  const noncash = received - cash;
  const change = received - order.total;
  const err = noncash > order.total ? t('restOrd.noncashTooMuch') : received < order.total ? t('restOrd.notEnough') : '';
  const setRow = (i, k, v) => setRows(rs => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const fill = type => setRows([{ type, amount: String(Math.round(order.total)) }]);
  return (
    <Modal wide title={`${t('restOrd.payment')}: ${money(order.total)}`} onClose={onClose}>
      <div className="flex flex-wrap gap-1">
        {['cash', 'card', 'click', 'payme'].map(tp => (
          <button key={tp} className="px-2.5 py-1 rounded-lg bg-slate-100 text-xs font-semibold text-slate-700" onClick={() => fill(tp)}>{t(`restOrd.pay.${tp}`)}</button>
        ))}
      </div>
      {rows.map((r, i) => (
        <div key={i} className="flex gap-2">
          <select className={`${inputCls} w-36`} value={r.type} onChange={e => setRow(i, 'type', e.target.value)}>
            {PAY_TYPES.map(tp => <option key={tp} value={tp}>{t(`restOrd.pay.${tp}`)}</option>)}
          </select>
          <input className={inputCls} inputMode="decimal" value={r.amount} onChange={e => setRow(i, 'amount', e.target.value)} />
          {rows.length > 1 && <button className="p-2 text-slate-400 hover:text-rose-600" onClick={() => setRows(rs => rs.filter((_, j) => j !== i))}><Trash2 className="w-4 h-4" /></button>}
        </div>
      ))}
      <button className="text-xs text-blue-700 font-semibold" onClick={() => setRows(rs => [...rs, { type: 'card', amount: String(Math.max(0, Math.round(order.total - received))) }])}>
        + {t('restOrd.addPayment')}
      </button>
      <label className="block">
        <span className="block text-xs font-semibold text-slate-600 mb-1">{t('restOrd.tips')}</span>
        <input className={inputCls} inputMode="decimal" value={tips} onChange={e => setTips(e.target.value)} placeholder="0" />
      </label>
      <div className="text-sm space-y-0.5">
        <div className="flex justify-between text-slate-600"><span>{t('restOrd.received')}</span><span className="tabular-nums">{money(received)}</span></div>
        <div className="flex justify-between font-bold text-slate-800"><span>{t('restOrd.change')}</span><span className="tabular-nums">{money(Math.max(0, change))}</span></div>
      </div>
      {err && <p className="text-xs text-rose-600">{err}</p>}
      <div className="flex justify-end gap-2">
        <button className={btnGhost} onClick={onClose}>{t('restOrd.back')}</button>
        <button className={btnPrimary} disabled={busy || !!err}
                onClick={() => onPay({ payments: rows.filter(r => num(r.amount) > 0).map(r => ({ type: r.type, amount: num(r.amount) })), tips: num(tips) })}>
          {t('restOrd.payConfirm')}
        </button>
      </div>
    </Modal>
  );
}
const TABLE_STYLE = {
  free: 'border-slate-300 bg-white text-slate-600',
  busy: 'border-blue-500 bg-blue-50 text-blue-800',
  ready: 'border-emerald-600 bg-emerald-50 text-emerald-800',
  precheck: 'border-amber-500 bg-amber-50 text-amber-800',
};
const ITEM_BADGE = {
  draft: 'bg-slate-100 text-slate-600', sent: 'bg-blue-50 text-blue-700', cooking: 'bg-orange-50 text-orange-700',
  ready: 'bg-emerald-50 text-emerald-700', served: 'bg-slate-50 text-slate-500', cancelled: 'bg-rose-50 text-rose-600',
};

const money = v => (Number(v) || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 0 });
const qtyFmt = v => (Number(v) || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 3 });
const btn = 'inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold disabled:opacity-50';
const btnPrimary = `${btn} bg-blue-600 hover:bg-blue-700 text-white`;
const btnGhost = `${btn} border border-slate-200 bg-white hover:bg-slate-50 text-slate-700`;
const inputCls = 'w-full px-3 py-2 border border-slate-200 rounded-lg bg-white text-sm text-slate-800 focus:outline-none focus:border-blue-500';

function Modal({ title, onClose, children, wide }) {
  return (
    <div className="fixed inset-0 z-[60] bg-slate-900/40 flex items-start justify-center overflow-y-auto p-4" onMouseDown={onClose}>
      <div className={`bg-white rounded-xl border border-slate-200 w-full ${wide ? 'max-w-md' : 'max-w-sm'} mt-16`} onMouseDown={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
          <h3 className="text-sm font-bold text-slate-800">{title}</h3>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-4 space-y-3">{children}</div>
      </div>
    </div>
  );
}

// ── menejer tasdig'i: tasdiqlovchini tanlash + PIN ──
function ApprovalModal({ capability, onCancel, onConfirm, t }) {
  const [list, setList] = useState(null);
  const [userId, setUserId] = useState('');
  const [pin, setPin] = useState('');
  useEffect(() => {
    api.get('/restaurant/approvers', { params: { capability } })
      .then(r => { setList(r.data); if (r.data.length === 1) setUserId(String(r.data[0].id)); })
      .catch(() => setList([]));
  }, [capability]);
  return (
    <Modal title={t('restOrd.approvalTitle')} onClose={onCancel}>
      <p className="text-xs text-slate-500">{t('restOrd.approvalHint')}</p>
      {list && list.length === 0 && <p className="text-sm text-rose-600">{t('restOrd.noApprovers')}</p>}
      {list && list.length > 0 && (
        <>
          <select className={inputCls} value={userId} onChange={e => setUserId(e.target.value)}>
            <option value="">{t('restOrd.chooseApprover')}</option>
            {list.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
          <input className={inputCls} type="password" inputMode="numeric" autoComplete="off" maxLength={6}
                 placeholder="PIN" value={pin} onChange={e => setPin(e.target.value.replace(/\D/g, ''))}
                 onKeyDown={e => { if (e.key === 'Enter' && userId && pin.length >= 4) onConfirm({ user_id: Number(userId), pin }); }} />
        </>
      )}
      <div className="flex justify-end gap-2">
        <button className={btnGhost} onClick={onCancel}>{t('restOrd.cancel')}</button>
        <button className={btnPrimary} disabled={!userId || pin.length < 4} onClick={() => onConfirm({ user_id: Number(userId), pin })}>{t('restOrd.confirm')}</button>
      </div>
    </Modal>
  );
}

function PinModal({ onClose, t }) {
  const [password, setPassword] = useState('');
  const [pin, setPin] = useState('');
  const save = async () => {
    try {
      await api.put('/restaurant/me/pin', { pin, password });
      toast.success(t('restOrd.pinSaved'));
      onClose();
    } catch (err) { toast.error(err.response?.data?.detail || t('restOrd.failed')); }
  };
  return (
    <Modal title={t('restOrd.myPin')} onClose={onClose}>
      <p className="text-xs text-slate-500">{t('restOrd.pinHint')}</p>
      <input className={inputCls} type="password" placeholder={t('restOrd.accountPassword')} value={password} onChange={e => setPassword(e.target.value)} />
      <input className={inputCls} type="password" inputMode="numeric" maxLength={6} placeholder={t('restOrd.newPin')} value={pin} onChange={e => setPin(e.target.value.replace(/\D/g, ''))} />
      <div className="flex justify-end gap-2">
        <button className={btnGhost} onClick={onClose}>{t('restOrd.cancel')}</button>
        <button className={btnPrimary} disabled={!password || pin.length < 4} onClick={save}>{t('restOrd.save')}</button>
      </div>
    </Modal>
  );
}

function PrecheckView({ order, onClose, t }) {
  const live = order.items.filter(i => i.status !== 'cancelled');
  return (
    <Modal title={t('restOrd.precheck')} onClose={onClose}>
      <div id="rest-precheck" className="font-mono text-xs text-slate-800 space-y-1">
        <div className="text-center font-bold">#{order.daily_no} {order.table_name ? `${t('restOrd.table')} ${order.table_name}` : ''}</div>
        <div className="text-center text-slate-500">{order.waiter_name} · {new Date().toLocaleString()}</div>
        <div className="border-t border-dashed border-slate-300 my-1" />
        {live.map(i => (
          <div key={i.id}>
            <div className="flex justify-between gap-2"><span>{i.name} x{qtyFmt(i.quantity)}</span><span>{money(i.amount)}</span></div>
            {i.modifiers?.length > 0 && <div className="pl-2 text-slate-500">{i.modifiers.map(m => (m.price ? `${m.name} +${money(m.price)}` : m.name)).join(', ')}</div>}
          </div>
        ))}
        <div className="border-t border-dashed border-slate-300 my-1" />
        <div className="flex justify-between"><span>{t('restOrd.subtotal')}</span><span>{money(order.subtotal)}</span></div>
        {order.discount_amount > 0 && <div className="flex justify-between"><span>{t('restOrd.discount')}</span><span>-{money(order.discount_amount)}</span></div>}
        {order.service_amount > 0 && <div className="flex justify-between"><span>{t('restOrd.service')} {order.service_pct}%</span><span>{money(order.service_amount)}</span></div>}
        <div className="flex justify-between font-bold text-sm"><span>{t('restOrd.total')}</span><span>{money(order.total)}</span></div>
      </div>
      <div className="flex justify-end gap-2">
        <button className={btnGhost} onClick={onClose}>{t('restOrd.close')}</button>
        <button className={btnPrimary} onClick={() => window.print()}><Printer className="w-4 h-4" />{t('restOrd.print')}</button>
      </div>
    </Modal>
  );
}

// R1.3: taom qo'shimchalarini tanlash. max_select = 1 bo'lsa radio kabi ishlaydi; majburiy guruh to'lmaguncha
// "Qo'shish" yopiq. Backend (resolve) shu qoidalarni qayta tekshiradi.
function ModifierPicker({ dish, groups, initial, onClose, onConfirm, t }) {
  const [picked, setPicked] = useState(initial || []);
  const toggle = (g, m) => setPicked(p => {
    if (p.includes(m.id)) return p.filter(x => x !== m.id);
    const inGroup = g.modifiers.map(x => x.id);
    if (g.max_select === 1) return [...p.filter(x => !inGroup.includes(x)), m.id];
    if (p.filter(x => inGroup.includes(x)).length >= g.max_select) return p;
    return [...p, m.id];
  });
  const missing = groups.filter(g => g.modifiers.filter(m => picked.includes(m.id)).length < g.min_select);
  const extra = groups.flatMap(g => g.modifiers).filter(m => picked.includes(m.id)).reduce((s, m) => s + (m.price || 0), 0);
  return (
    <Modal title={dish.name} onClose={onClose}>
      <div className="space-y-3 max-h-[60vh] overflow-y-auto">
        {groups.map(g => (
          <div key={g.id}>
            <div className="text-sm font-semibold text-slate-800">
              {g.name}
              <span className={`ml-2 text-xs font-normal ${g.min_select > 0 ? 'text-amber-700' : 'text-slate-500'}`}>
                {g.min_select > 0 ? t('restMod.required') : t('restMod.optional')}{g.max_select > 1 ? `, ${t('restMod.upTo')} ${g.max_select}` : ''}
              </span>
            </div>
            <div className="flex flex-wrap gap-2 mt-1.5">
              {g.modifiers.filter(m => m.is_active).map(m => (
                <button key={m.id} type="button" onClick={() => toggle(g, m)}
                        className={`px-3 py-2 rounded-lg border text-sm ${picked.includes(m.id) ? 'border-blue-600 bg-blue-50 text-blue-800 font-semibold' : 'border-slate-200 text-slate-700'}`}>
                  {m.name}{m.price ? <span className="ml-1 text-xs text-slate-500">+{money(m.price)}</span> : null}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-100">
        <span className="text-sm tabular-nums text-slate-700">{money((dish.sale_price || 0) + extra)}</span>
        <div className="flex gap-2">
          <button className={btnGhost} onClick={onClose}>{t('restOrd.back')}</button>
          <button className={btnPrimary} disabled={missing.length > 0} onClick={() => onConfirm(picked)}>
            {initial ? t('restMod.apply') : t('restMod.addToCheck')}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ── chek oynasi ──
function OrderPanel({ orderId, menu, categories, tables, onClose, onChanged, t }) {
  const [order, setOrder] = useState(null);
  const [cat, setCat] = useState('');
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [approval, setApproval] = useState(null);   // {capability, run}
  const [cancelFor, setCancelFor] = useState(null); // {item|null}
  const [reason, setReason] = useState('guest_refused');
  const [note, setNote] = useState('');
  const [discountOpen, setDiscountOpen] = useState(false);
  const [disc, setDisc] = useState({ pct: '', reason: '' });
  const [moveOpen, setMoveOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(null);  // list of candidate orders
  const [showPrecheck, setShowPrecheck] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const [perms, setPerms] = useState(null);
  const [modGroups, setModGroups] = useState([]);
  const [picker, setPicker] = useState(null);   // {dish, item?}
  useEffect(() => { api.get('/restaurant/me/perms', { _silent: true }).then(r => setPerms(r.data)).catch(() => setPerms({})); }, []);
  useEffect(() => {
    api.get('/restaurant/modifier-groups', { params: { include_inactive: false }, _silent: true })
      .then(r => setModGroups(r.data)).catch(() => setModGroups([]));
  }, []);

  const load = useCallback(() => api.get(`/restaurant/orders/${orderId}`).then(r => setOrder(r.data))
    .catch(err => toast.error(err.response?.data?.detail || t('restOrd.failed'))), [orderId, t]);
  useEffect(() => { load(); }, [load]);

  // Barcha o'zgartirishlar shu orqali: versiya, 409 va tasdiq oynasi bir joyda
  const call = useCallback(async (method, path, body, capability, approvalData) => {
    setBusy(true);
    try {
      const payload = approvalData ? { ...(body || {}), approval: approvalData } : body;
      const r = await api.request({ method, url: `/restaurant/orders/${orderId}${path}`, data: payload,
                                    params: { version: order?.version } });
      setOrder(r.data);
      onChanged();
      return r.data;
    } catch (err) {
      const d = err.response?.data?.detail;
      if (err.response?.status === 403 && d?.code === 'APPROVAL_REQUIRED' && capability) {
        setApproval({ capability, run: a => call(method, path, body, capability, a) });
      } else if (err.response?.status === 409 && d?.code === 'ORDER_CHANGED') {
        toast.error(d.message); load();
      } else {
        toast.error((typeof d === 'object' ? d?.message : d) || t('restOrd.failed'));
      }
      return null;
    } finally {
      setBusy(false);
    }
  }, [orderId, order?.version, onChanged, load, t]);

  const shownMenu = useMemo(() => {
    const s = q.trim().toLowerCase();
    return menu.filter(m => (!cat || String(m.category_id) === cat) && (!s || m.name.toLowerCase().includes(s)));
  }, [menu, cat, q]);

  if (!order) return null;
  const editable = order.status === 'open' || (order.status === 'prechecked' && !order.locked);
  const drafts = order.items.filter(i => i.status === 'draft');
  const draftCourses = [...new Set(drafts.map(i => i.course))].sort();

  const groupsOf = m => (m?.modifier_group_ids || []).map(id => modGroups.find(g => g.id === id)).filter(Boolean);
  const addDish = m => (groupsOf(m).length
    ? setPicker({ dish: m })
    : call('post', '/items', { items: [{ product_id: m.id, quantity: 1 }] }));
  const confirmPicker = ids => {
    const { dish, item } = picker;
    setPicker(null);
    if (item) return call('patch', `/items/${item.id}`, { modifiers: ids });
    return call('post', '/items', { items: [{ product_id: dish.id, quantity: 1, modifiers: ids }] });
  };
  const setQty = (i, d) => {
    const nq = Number(i.quantity) + d;
    if (nq <= 0) return call('post', `/items/${i.id}/cancel`, {});
    return call('patch', `/items/${i.id}`, { quantity: nq });
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex">
      <div className="bg-white w-full h-full flex flex-col lg:flex-row">
        {/* Menyu */}
        <div className="lg:w-[58%] flex flex-col border-r border-slate-200 min-h-0">
          <div className="p-3 border-b border-slate-100 space-y-2">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input className={`${inputCls} pl-9`} value={q} onChange={e => setQ(e.target.value)} placeholder={t('restOrd.searchDish')} />
            </div>
            <div className="flex gap-1 overflow-x-auto">
              <button onClick={() => setCat('')} className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap ${cat === '' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'}`}>{t('restOrd.all')}</button>
              {categories.map(c => (
                <button key={c.id} onClick={() => setCat(String(c.id))} className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap ${cat === String(c.id) ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'}`}>{c.name}</button>
              ))}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-3 grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-2 content-start">
            {shownMenu.map(m => (
              <button key={m.id} disabled={!editable || busy} onClick={() => addDish(m)}
                      className="text-left p-3 rounded-lg border border-slate-200 hover:border-blue-500 disabled:opacity-50 bg-white">
                <div className="text-sm font-semibold text-slate-800 leading-tight">{m.name}</div>
                <div className="text-xs text-slate-500 mt-1 tabular-nums">{money(m.sale_price)}</div>
              </button>
            ))}
            {shownMenu.length === 0 && <div className="col-span-full text-center text-sm text-slate-400 py-10">{t('restOrd.noDishes')}</div>}
          </div>
        </div>

        {/* Chek */}
        <div className="lg:w-[42%] flex flex-col min-h-0">
          <div className="px-4 py-3 border-b border-slate-100 flex items-start justify-between gap-2">
            <div>
              <div className="text-base font-bold text-slate-800">
                #{order.daily_no} {order.table_name ? `· ${t('restOrd.table')} ${order.table_name}` : `· ${t(`restOrd.type.${order.order_type}`)}`}
              </div>
              <div className="text-xs text-slate-500">
                {order.waiter_name} · {t('restOrd.guests')}: {order.guests}
                {order.status === 'prechecked' && <span className="ml-2 text-amber-700 font-semibold">{t('restOrd.precheckDone')}</span>}
              </div>
            </div>
            <button onClick={onClose} className="p-1.5 text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
            {order.items.length === 0 && <div className="text-center text-sm text-slate-400 py-10">{t('restOrd.emptyCheck')}</div>}
            {order.items.map(i => (
              <div key={i.id} className={`px-4 py-2 flex items-center gap-2 ${i.status === 'cancelled' ? 'opacity-50' : ''}`}>
                <div className="flex-1 min-w-0">
                  <div className={`text-sm font-medium text-slate-800 ${i.status === 'cancelled' ? 'line-through' : ''}`}>{i.name}</div>
                  {i.modifiers?.length > 0 && (
                    i.status === 'draft' && editable && groupsOf(menu.find(m => m.id === i.product_id)).length ? (
                      <button className="block text-left text-xs text-blue-700 hover:underline"
                              onClick={() => setPicker({ dish: menu.find(m => m.id === i.product_id), item: i })}>
                        {i.modifiers.map(m => m.name).join(', ')}
                      </button>
                    ) : (
                      <div className="text-xs text-slate-500">{i.modifiers.map(m => m.name).join(', ')}</div>
                    )
                  )}
                  <div className="flex flex-wrap items-center gap-1.5 mt-0.5">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${ITEM_BADGE[i.status]}`}>{t(`restOrd.item.${i.status}`)}</span>
                    {i.course > 1 && <span className="text-[10px] text-slate-500">{i.course}-{t('restOrd.course')}</span>}
                    {i.comment && <span className="text-[10px] text-slate-500 truncate">{i.comment}</span>}
                  </div>
                </div>
                {i.status === 'draft' && editable ? (
                  <div className="flex items-center gap-1">
                    <button className="p-1 rounded border border-slate-200" disabled={busy} onClick={() => setQty(i, -1)}><Minus className="w-3.5 h-3.5" /></button>
                    <span className="w-8 text-center text-sm tabular-nums">{qtyFmt(i.quantity)}</span>
                    <button className="p-1 rounded border border-slate-200" disabled={busy} onClick={() => setQty(i, 1)}><Plus className="w-3.5 h-3.5" /></button>
                    <select className="ml-1 text-xs border border-slate-200 rounded px-1 py-0.5" value={i.course}
                            onChange={e => call('patch', `/items/${i.id}`, { course: Number(e.target.value) })}>
                      {[1, 2, 3].map(c => <option key={c} value={c}>{c}-{t('restOrd.course')}</option>)}
                    </select>
                  </div>
                ) : (
                  <span className="text-sm tabular-nums text-slate-600">x{qtyFmt(i.quantity)}</span>
                )}
                <span className="w-20 text-right text-sm tabular-nums">{money(i.amount)}</span>
                {editable && i.status !== 'draft' && i.status !== 'cancelled' && (
                  <button title={t('restOrd.cancelItem')} className="p-1 text-slate-400 hover:text-rose-600" onClick={() => { setCancelFor({ item: i }); setReason('guest_refused'); setNote(''); }}><Ban className="w-4 h-4" /></button>
                )}
                {i.status === 'ready' && (
                  <button className="text-[11px] px-2 py-1 rounded bg-emerald-600 text-white" onClick={() => call('post', `/items/${i.id}/status`, { status: 'served' })}>{t('restOrd.served')}</button>
                )}
              </div>
            ))}
          </div>

          <div className="border-t border-slate-200 p-3 space-y-2">
            <div className="text-sm space-y-0.5">
              <div className="flex justify-between text-slate-600"><span>{t('restOrd.subtotal')}</span><span className="tabular-nums">{money(order.subtotal)}</span></div>
              {order.discount_amount > 0 && <div className="flex justify-between text-slate-600"><span>{t('restOrd.discount')}{order.discount_pct ? ` ${order.discount_pct}%` : ''}</span><span className="tabular-nums">-{money(order.discount_amount)}</span></div>}
              {order.service_amount > 0 && <div className="flex justify-between text-slate-600"><span>{t('restOrd.service')} {order.service_pct}%</span><span className="tabular-nums">{money(order.service_amount)}</span></div>}
              <div className="flex justify-between text-base font-bold text-slate-800"><span>{t('restOrd.total')}</span><span className="tabular-nums">{money(order.total)}</span></div>
            </div>

            {drafts.length > 0 && editable && (
              <div className="flex gap-2">
                <button className={`${btnPrimary} flex-1`} disabled={busy} onClick={() => call('post', '/send', {})}><Send className="w-4 h-4" />{t('restOrd.sendAll')}</button>
                {draftCourses.length > 1 && draftCourses.map(c => (
                  <button key={c} className={btnGhost} disabled={busy} onClick={() => call('post', '/send', { course: c })}>{c}-{t('restOrd.course')}</button>
                ))}
              </div>
            )}

            {(order.status === 'open' || order.status === 'prechecked') && perms?.take_payment && drafts.length === 0 && order.items.some(i => i.status !== 'cancelled') && (
              <button className={`${btn} w-full bg-emerald-600 hover:bg-emerald-700 text-white`} disabled={busy} onClick={() => setPayOpen(true)}>
                <Wallet className="w-4 h-4" />{t('restOrd.payment')} &middot; {money(order.total)}
              </button>
            )}

            <div className="grid grid-cols-3 gap-2">
              {order.status === 'open' && (
                <button className={btnGhost} disabled={busy} onClick={async () => { const o = await call('post', '/precheck'); if (o) setShowPrecheck(true); }}>
                  <Printer className="w-4 h-4" />{t('restOrd.precheck')}
                </button>
              )}
              {order.status === 'prechecked' && (
                <>
                  <button className={btnGhost} onClick={() => setShowPrecheck(true)}><Printer className="w-4 h-4" />{t('restOrd.print')}</button>
                  {order.locked && <button className={btnGhost} disabled={busy} onClick={() => call('post', '/unlock', {}, 'unlock_precheck')}><Unlock className="w-4 h-4" />{t('restOrd.unlock')}</button>}
                </>
              )}
              {editable && <button className={btnGhost} onClick={() => { setDisc({ pct: order.discount_pct ?? '', reason: order.discount_reason || '' }); setDiscountOpen(true); }}><Percent className="w-4 h-4" />{t('restOrd.discount')}</button>}
              <button className={btnGhost} onClick={() => setMoveOpen(true)}><ArrowRightLeft className="w-4 h-4" />{t('restOrd.move')}</button>
              {order.status === 'open' && (
                <button className={btnGhost} onClick={async () => {
                  const r = await api.get('/restaurant/orders', { params: { branch_id: order.branch_id, status: 'open' } });
                  setMergeOpen(r.data.filter(o => o.id !== order.id));
                }}><Merge className="w-4 h-4" />{t('restOrd.merge')}</button>
              )}
              <button className={`${btn} border border-rose-200 text-rose-600 hover:bg-rose-50`} onClick={() => { setCancelFor({ item: null }); setReason('guest_refused'); setNote(''); }}>
                <Ban className="w-4 h-4" />{t('restOrd.cancelOrder')}
              </button>
            </div>
            {order.locked && <p className="text-[11px] text-amber-700 flex items-center gap-1"><Lock className="w-3 h-3" />{t('restOrd.lockedHint')}</p>}
          </div>
        </div>
      </div>

      {cancelFor && (
        <Modal title={cancelFor.item ? `${t('restOrd.cancelItem')}: ${cancelFor.item.name}` : t('restOrd.cancelOrder')} onClose={() => setCancelFor(null)}>
          <select className={inputCls} value={reason} onChange={e => setReason(e.target.value)}>
            {REASONS.map(r => <option key={r} value={r}>{t(`restOrd.reason.${r}`)}</option>)}
          </select>
          <input className={inputCls} value={note} maxLength={250} placeholder={t('restOrd.note')} onChange={e => setNote(e.target.value)} />
          <div className="flex justify-end gap-2">
            <button className={btnGhost} onClick={() => setCancelFor(null)}>{t('restOrd.back')}</button>
            <button className={`${btn} bg-rose-600 hover:bg-rose-700 text-white`} disabled={busy} onClick={async () => {
              const path = cancelFor.item ? `/items/${cancelFor.item.id}/cancel` : '/cancel';
              setCancelFor(null);
              const o = await call('post', path, { reason, note }, 'cancel_sent');
              if (o && o.status === 'cancelled') onClose();
            }}>{t('restOrd.doCancel')}</button>
          </div>
        </Modal>
      )}

      {discountOpen && (
        <Modal title={t('restOrd.discount')} onClose={() => setDiscountOpen(false)}>
          <input className={inputCls} inputMode="decimal" placeholder={t('restOrd.discountPct')} value={disc.pct}
                 onChange={e => setDisc(d => ({ ...d, pct: e.target.value }))} />
          <input className={inputCls} placeholder={t('restOrd.discountReason')} value={disc.reason} maxLength={200}
                 onChange={e => setDisc(d => ({ ...d, reason: e.target.value }))} />
          <div className="flex justify-end gap-2">
            <button className={btnGhost} onClick={() => setDiscountOpen(false)}>{t('restOrd.back')}</button>
            <button className={btnPrimary} disabled={busy} onClick={async () => {
              setDiscountOpen(false);
              await call('post', '/discount', { pct: Number(String(disc.pct || 0).replace(',', '.')), reason: disc.reason }, 'discount');
            }}>{t('restOrd.apply')}</button>
          </div>
        </Modal>
      )}

      {moveOpen && (
        <Modal title={t('restOrd.moveTo')} onClose={() => setMoveOpen(false)}>
          <div className="grid grid-cols-4 gap-2 max-h-72 overflow-y-auto">
            {tables.filter(x => x.id !== order.table_id).map(x => (
              <button key={x.id} className={btnGhost} onClick={async () => { setMoveOpen(false); await call('post', '/move', { table_id: x.id }); }}>{x.name}</button>
            ))}
          </div>
        </Modal>
      )}

      {mergeOpen && (
        <Modal title={t('restOrd.mergeFrom')} onClose={() => setMergeOpen(null)}>
          {mergeOpen.length === 0 && <p className="text-sm text-slate-500">{t('restOrd.noOtherOrders')}</p>}
          <div className="space-y-1 max-h-72 overflow-y-auto">
            {mergeOpen.map(o => (
              <button key={o.id} className={`${btnGhost} w-full justify-between`} onClick={async () => { setMergeOpen(null); await call('post', '/merge', { source_order_id: o.id }); }}>
                <span>#{o.daily_no} {o.table_name ? `· ${t('restOrd.table')} ${o.table_name}` : ''}</span>
                <span className="tabular-nums">{money(o.total)}</span>
              </button>
            ))}
          </div>
        </Modal>
      )}

      {approval && (
        <ApprovalModal capability={approval.capability} t={t} onCancel={() => setApproval(null)}
                       onConfirm={a => { const run = approval.run; setApproval(null); run(a); }} />
      )}
      {showPrecheck && <PrecheckView order={order} t={t} onClose={() => setShowPrecheck(false)} />}
      {picker?.dish && (
        <ModifierPicker dish={picker.dish} groups={groupsOf(picker.dish)} t={t}
                        initial={picker.item ? picker.item.modifiers.map(m => m.id) : null}
                        onClose={() => setPicker(null)} onConfirm={confirmPicker} />
      )}
      {payOpen && (
        <PayModal order={order} busy={busy} t={t} onClose={() => setPayOpen(false)}
                  onPay={async body => {
                    const res = await call('post', '/pay', body);
                    if (!res) return;
                    setPayOpen(false);
                    toast.success(res.change > 0 ? `${t('restOrd.paid')}. ${t('restOrd.change')}: ${money(res.change)}` : t('restOrd.paid'));
                    await sendFiscal(res.fiscal, t);
                    onClose();
                  }} />
      )}
    </div>
  );
}

// R5.4: to'langan chekni qaytarish oynasi (to'liq yoki qatorlar bo'yicha). Taom omborga qaytmaydi,
// tovar faqat "omborga qaytarish" belgilansa. Ruxsat yetmasa menejer PIN tasdig'i so'raladi.
const REFUND_REASONS = ['quality', 'guest_refused', 'mistake', 'long_wait', 'other'];
const REFUND_PAY = ['cash', 'card', 'uzcard', 'humo', 'click', 'payme', 'uzum'];

function RefundModal({ order, onClose, onDone, t }) {
  const [lines, setLines] = useState(() => order.items
    .filter(i => i.status !== 'cancelled' && Number(i.quantity) - Number(i.refunded_qty || 0) > 0)
    .map(i => {
      const max = Number(i.quantity) - Number(i.refunded_qty || 0);
      return { item_id: i.id, name: i.name, max, qty: String(max), on: true, restock: false };
    }));
  const [reason, setReason] = useState('quality');
  const [payType, setPayType] = useState((order.payments?.[0]?.type) || 'cash');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [approval, setApproval] = useState(null);

  const setLine = (i, k, v) => setLines(ls => ls.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  const chosen = lines.filter(l => l.on && num(l.qty) > 0);
  const isFull = chosen.length === lines.length && chosen.every(l => num(l.qty) === l.max);

  const submit = async (approvalData) => {
    const body = { reason, note, payment_type: payType };
    if (!isFull) body.lines = chosen.map(l => ({ item_id: l.item_id, quantity: num(l.qty), restock: l.restock }));
    else body.lines = lines.filter(l => l.restock).length
      ? lines.map(l => ({ item_id: l.item_id, quantity: l.max, restock: l.restock })) : null;
    if (approvalData) body.approval = approvalData;
    setBusy(true);
    try {
      const r = await api.post(`/restaurant/orders/${order.id}/refund`, body, { params: { version: order.version } });
      toast.success(`${t('restOrd.refundDone')}: ${money(r.data.refund.amount)}`);
      const factoryId = fiscalFactoryId();
      if (factoryId && r.data.refund.fiscal_cart?.length) {
        try {
          await registerReturn({ factoryId, cart: r.data.refund.fiscal_cart, discountAmount: 0 });
          toast.success(t('restOrd.fiscalSent'));
        } catch (err) { toast.error(`${t('restOrd.fiscalReturnFailed')}: ${err?.message || ''}`); }
      }
      onDone();
    } catch (err) {
      const d = err.response?.data?.detail;
      if (err.response?.status === 403 && d?.code === 'APPROVAL_REQUIRED') setApproval(true);
      else toast.error((typeof d === 'object' ? d?.message : d) || t('restOrd.failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal wide title={`${t('restOrd.refundTitle')}: #${order.daily_no}`} onClose={onClose}>
      {lines.length === 0 && <p className="text-sm text-slate-500">{t('restOrd.nothingToRefund')}</p>}
      <div className="space-y-1 max-h-64 overflow-y-auto">
        {lines.map((l, i) => (
          <div key={l.item_id} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={l.on} onChange={e => setLine(i, 'on', e.target.checked)} />
            <span className="flex-1 truncate">{l.name}</span>
            <input className="w-16 px-2 py-1 border border-slate-200 rounded text-right" inputMode="decimal" value={l.qty}
                   disabled={!l.on} onChange={e => setLine(i, 'qty', e.target.value)} />
            <span className="text-xs text-slate-400 w-10">/ {qtyFmt(l.max)}</span>
            <label className="flex items-center gap-1 text-[11px] text-slate-500" title={t('restOrd.restockHint')}>
              <input type="checkbox" checked={l.restock} disabled={!l.on} onChange={e => setLine(i, 'restock', e.target.checked)} />
              {t('restOrd.restock')}
            </label>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <select className={inputCls} value={reason} onChange={e => setReason(e.target.value)}>
          {REFUND_REASONS.map(r => <option key={r} value={r}>{t(`restOrd.refundReason.${r}`)}</option>)}
        </select>
        <select className={inputCls} value={payType} onChange={e => setPayType(e.target.value)}>
          {REFUND_PAY.map(p => <option key={p} value={p}>{t(`restOrd.pay.${p}`)}</option>)}
        </select>
      </div>
      <input className={inputCls} value={note} maxLength={200} placeholder={t('restOrd.note')} onChange={e => setNote(e.target.value)} />
      <p className="text-[11px] text-slate-500">{t('restOrd.refundHint')}</p>
      <div className="flex justify-end gap-2">
        <button className={btnGhost} onClick={onClose}>{t('restOrd.back')}</button>
        <button className={`${btn} bg-rose-600 hover:bg-rose-700 text-white`} disabled={busy || chosen.length === 0} onClick={() => submit(null)}>
          {t('restOrd.refund')}
        </button>
      </div>
      {approval && (
        <ApprovalModal capability="cancel_sent" t={t} onCancel={() => setApproval(null)}
                       onConfirm={a => { setApproval(null); submit(a); }} />
      )}
    </Modal>
  );
}

export default function RestaurantOrders() {
  const { t } = useLang();
  const { branches, currentBranchId, assignedBranchId } = useBranch();
  const [branchId, setBranchId] = useState(null);
  const [halls, setHalls] = useState([]);
  const [hallId, setHallId] = useState(null);
  const [status, setStatus] = useState({});        // table_id -> {status, orders}
  const [openOrders, setOpenOrders] = useState([]);
  const [closedOrders, setClosedOrders] = useState([]);   // R5.4: bugun yopilgan cheklar
  const [refundFor, setRefundFor] = useState(null);
  const [menu, setMenu] = useState([]);
  const [categories, setCategories] = useState([]);
  const [orderId, setOrderId] = useState(null);
  const [choose, setChoose] = useState(null);      // {table, orders}
  const [newFor, setNewFor] = useState(null);      // {table|null, order_type}
  const [guests, setGuests] = useState('2');
  const [pinOpen, setPinOpen] = useState(false);
  const timer = useRef(null);
  // R4.2: oshxonada taom tayyor bo'lganda xabar (holat 'ready' ga o'tgan stol); birinchi yuklashda xabar yo'q
  const prevStatus = useRef(null);
  const hallsRef = useRef([]);

  useEffect(() => {
    if (branchId) return;
    const b = currentBranchId ?? assignedBranchId ?? branches?.[0]?.id ?? null;
    if (b) setBranchId(b);
  }, [branchId, currentBranchId, assignedBranchId, branches]);

  const refresh = useCallback(() => {
    if (!branchId) return;
    api.get('/restaurant/tables/status', { params: { branch_id: branchId }, _silent: true })
      .then(r => {
        const next = Object.fromEntries(r.data.map(x => [x.table_id, x]));
        const prev = prevStatus.current;
        if (prev) {
          const names = Object.fromEntries(hallsRef.current.flatMap(h => h.tables).map(x => [x.id, x.name]));
          for (const [tid, st] of Object.entries(next)) {
            if (st.status === 'ready' && prev[tid]?.status !== 'ready') {
              toast.success(`${t('restOrd.readyNotice')}: ${t('restOrd.table')} ${names[tid] || tid}`, { duration: 6000 });
            }
          }
        }
        prevStatus.current = next;
        setStatus(next);
      }).catch(() => {});
    api.get('/restaurant/orders', { params: { branch_id: branchId }, _silent: true })
      .then(r => setOpenOrders(r.data)).catch(() => {});
    api.get('/restaurant/orders', { params: { branch_id: branchId, status: 'paid', closed_today: true }, _silent: true })
      .then(r => setClosedOrders(r.data)).catch(() => {});
  }, [branchId]);

  useEffect(() => {
    if (!branchId) return;
    api.get('/restaurant/halls', { params: { branch_id: branchId } }).then(r => {
      setHalls(r.data);
      hallsRef.current = r.data;
      setHallId(h => (r.data.some(x => x.id === h) ? h : r.data[0]?.id ?? null));
    }).catch(err => toast.error(err.response?.data?.detail || t('restOrd.failed')));
    refresh();
    clearInterval(timer.current);
    timer.current = setInterval(refresh, 15000);
    return () => clearInterval(timer.current);
  }, [branchId, refresh, t]);

  useEffect(() => {
    api.get('/restaurant/menu/items', { params: { kind: 'dish,goods' } }).then(r => setMenu(r.data)).catch(() => {});
    api.get('/restaurant/menu/categories').then(r => setCategories(r.data)).catch(() => {});
  }, []);

  const hall = halls.find(h => h.id === hallId);
  const allTables = useMemo(() => halls.flatMap(h => h.tables), [halls]);
  const size = useMemo(() => {
    const ts = hall?.tables || [];
    return { w: Math.max(24, ...ts.map(x => x.x + x.w + 1)), h: Math.max(14, ...ts.map(x => x.y + x.h + 1)) };
  }, [hall]);
  const noTableOrders = openOrders.filter(o => !o.table_id);

  const clickTable = tb => {
    const st = status[tb.id];
    if (!st || st.orders.length === 0) { setGuests(String(Math.min(tb.seats, 2) || 2)); setNewFor({ table: tb, order_type: 'dine_in' }); return; }
    if (st.orders.length === 1) { setOrderId(st.orders[0].id); return; }
    setChoose({ table: tb, orders: st.orders });
  };

  const create = async () => {
    try {
      const body = { order_type: newFor.order_type, guests: Number(guests) || 1, branch_id: branchId };
      if (newFor.table) body.table_id = newFor.table.id;
      const r = await api.post('/restaurant/orders', body);
      setNewFor(null);
      setChoose(null);
      setOrderId(r.data.id);
      refresh();
    } catch (err) { toast.error(err.response?.data?.detail || t('restOrd.failed')); }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold text-slate-800">{t('restOrd.title')}</h1>
          <p className="text-sm text-slate-500">{t('restOrd.desc')}</p>
        </div>
        <div className="flex gap-2">
          {branches.length > 1 && (
            <select className="px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white" value={branchId ?? ''} onChange={e => setBranchId(Number(e.target.value))}>
              {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          )}
          <button className={btnGhost} onClick={() => setPinOpen(true)}><KeyRound className="w-4 h-4" />{t('restOrd.myPin')}</button>
          <button className={btnPrimary} onClick={() => { setGuests('1'); setNewFor({ table: null, order_type: 'takeaway' }); }}><ShoppingBag className="w-4 h-4" />{t('restOrd.takeaway')}</button>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 text-[11px] text-slate-500">
        {['free', 'busy', 'ready', 'precheck'].map(s => (
          <span key={s} className="inline-flex items-center gap-1"><span className={`w-3 h-3 rounded border-2 ${TABLE_STYLE[s]}`} />{t(`restOrd.st.${s}`)}</span>
        ))}
      </div>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {halls.map(h => (
          <button key={h.id} onClick={() => setHallId(h.id)} className={`px-3 py-2 text-sm font-semibold border-b-2 -mb-px ${h.id === hallId ? 'border-blue-600 text-blue-700' : 'border-transparent text-slate-500'}`}>{h.name}</button>
        ))}
      </div>

      <div className="grid lg:grid-cols-[1fr_260px] gap-3 items-start">
        <div className="bg-white border border-slate-200 rounded-xl overflow-auto p-3" style={{ maxHeight: '72vh' }}>
          {!hall && <div className="py-10 text-center text-sm text-slate-400">{t('restOrd.noHall')}</div>}
          {hall && (
            <div className="relative" style={{ width: size.w * CELL, height: size.h * CELL }}>
              {hall.tables.map(tb => {
                const st = status[tb.id];
                const s = st?.status || 'free';
                const o = st?.orders?.[0];
                return (
                  <button key={tb.id} onClick={() => clickTable(tb)}
                          className={`absolute border-2 flex flex-col items-center justify-center ${TABLE_STYLE[s]} ${tb.shape === 'round' ? 'rounded-full' : 'rounded-lg'}`}
                          style={{ left: tb.x * CELL + 2, top: tb.y * CELL + 2, width: tb.w * CELL - 4, height: tb.h * CELL - 4 }}>
                    <span className="text-sm font-bold leading-none">{tb.name}</span>
                    {o && <span className="text-[10px] leading-tight mt-0.5 tabular-nums">{money(o.total)}</span>}
                    {o && <span className="text-[9px] leading-tight opacity-75">{o.minutes ?? 0}{t('restOrd.min')}{st.orders.length > 1 ? ` +${st.orders.length - 1}` : ''}</span>}
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <div className="bg-white border border-slate-200 rounded-xl">
          <div className="px-3 py-2 border-b border-slate-100 text-sm font-bold text-slate-800">{t('restOrd.withoutTable')}</div>
          <div className="divide-y divide-slate-100 max-h-[60vh] overflow-y-auto">
            {noTableOrders.length === 0 && <div className="px-3 py-4 text-xs text-slate-400">{t('restOrd.none')}</div>}
            {noTableOrders.map(o => (
              <button key={o.id} onClick={() => setOrderId(o.id)} className="w-full px-3 py-2 flex justify-between text-sm hover:bg-slate-50">
                <span>#{o.daily_no} · {t(`restOrd.type.${o.order_type}`)}</span><span className="tabular-nums">{money(o.total)}</span>
              </button>
            ))}
          </div>
          <div className="px-3 py-2 border-y border-slate-100 text-sm font-bold text-slate-800">{t('restOrd.closedToday')}</div>
          <div className="divide-y divide-slate-100 max-h-[40vh] overflow-y-auto">
            {closedOrders.length === 0 && <div className="px-3 py-4 text-xs text-slate-400">{t('restOrd.none')}</div>}
            {closedOrders.map(o => (
              <div key={o.id} className="px-3 py-2 flex items-center gap-2 text-sm">
                <div className="flex-1 min-w-0">
                  <div className="truncate">#{o.daily_no}{o.table_name ? ` · ${t('restOrd.table')} ${o.table_name}` : ''}</div>
                  {o.refunded_amount > 0 && <div className="text-[11px] text-rose-600">{t('restOrd.refunded')}: {money(o.refunded_amount)}</div>}
                </div>
                <span className="tabular-nums">{money(o.total)}</span>
                {o.refunded_amount < o.total && (
                  <button className="text-[11px] px-2 py-1 rounded border border-rose-200 text-rose-600 hover:bg-rose-50" onClick={() => setRefundFor(o)}>
                    {t('restOrd.refund')}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {choose && (
        <Modal title={`${t('restOrd.table')} ${choose.table.name}`} onClose={() => setChoose(null)}>
          {choose.orders.map(o => (
            <button key={o.id} className={`${btnGhost} w-full justify-between`} onClick={() => { setChoose(null); setOrderId(o.id); }}>
              <span>#{o.daily_no} · {o.waiter_name}</span><span className="tabular-nums">{money(o.total)}</span>
            </button>
          ))}
          <button className={`${btnPrimary} w-full`} onClick={() => { setNewFor({ table: choose.table, order_type: 'dine_in' }); setChoose(null); }}><Plus className="w-4 h-4" />{t('restOrd.newCheck')}</button>
        </Modal>
      )}

      {newFor && (
        <Modal title={newFor.table ? `${t('restOrd.table')} ${newFor.table.name}: ${t('restOrd.newCheck')}` : t('restOrd.takeaway')} onClose={() => setNewFor(null)}>
          {newFor.table && (
            <label className="block">
              <span className="block text-xs font-semibold text-slate-600 mb-1">{t('restOrd.guests')}</span>
              <input className={inputCls} inputMode="numeric" value={guests} autoFocus onChange={e => setGuests(e.target.value.replace(/\D/g, ''))} onKeyDown={e => { if (e.key === 'Enter') create(); }} />
            </label>
          )}
          <div className="flex justify-end gap-2">
            <button className={btnGhost} onClick={() => setNewFor(null)}>{t('restOrd.cancel')}</button>
            <button className={btnPrimary} onClick={create}>{t('restOrd.openCheck')}</button>
          </div>
        </Modal>
      )}

      {orderId && (
        <OrderPanel orderId={orderId} menu={menu} categories={categories} tables={allTables} t={t}
                    onClose={() => { setOrderId(null); refresh(); }} onChanged={refresh} />
      )}
      {pinOpen && <PinModal t={t} onClose={() => setPinOpen(false)} />}
      {refundFor && <RefundModal order={refundFor} t={t} onClose={() => setRefundFor(null)} onDone={() => { setRefundFor(null); refresh(); }} />}
    </div>
  );
}
