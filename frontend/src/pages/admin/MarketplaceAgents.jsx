import { useState, useEffect, useCallback } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import toast from 'react-hot-toast';

// T3.17: Marketplace agentlari — ro'yxat, status, balans va kassadan to'lov

const fmt = (v) => Number(v || 0).toLocaleString('uz-UZ', { maximumFractionDigits: 2 });

const STATUS_STYLE = {
  active: 'bg-emerald-100 text-emerald-800',
  pending: 'bg-amber-100 text-amber-800',
  blocked: 'bg-red-100 text-red-800',
};

export default function MarketplaceAgents() {
  const { t } = useLang();
  // Yangi matnlar: i18n kaliti, bo'lmasa o'zbekcha zaxira
  const tf = (key, fallback) => { const v = t(key); return v === key ? fallback : v; };

  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');

  const [balanceView, setBalanceView] = useState(null); // { agent, data }
  const [payAgent, setPayAgent] = useState(null);
  const [wallets, setWallets] = useState([]);
  const [payForm, setPayForm] = useState({ amount: '', wallet_id: '', payment_type: 'cash', note: '' });
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState('');

  const statusLabel = (s) => ({
    active: tf('mpAgents.statusActive', 'Faol'),
    pending: tf('mpAgents.statusPending', 'Kutilmoqda'),
    blocked: tf('mpAgents.statusBlocked', 'Bloklangan'),
  }[s] || s);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (status) params.status = status;
      if (q.trim()) params.q = q.trim();
      const { data } = await api.get('/marketplace-agents', { params, _suppressToast: true });
      setItems(data.items || []);
    } catch (e) {
      setItems([]);
      toast.error(e.response?.data?.detail || tf('mpAgents.loadError', "Agentlarni yuklab bo'lmadi"));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, q]);

  useEffect(() => {
    const id = setTimeout(load, q ? 300 : 0);
    return () => clearTimeout(id);
  }, [load, q]);

  const changeStatus = async (agent, next) => {
    try {
      await api.put(`/marketplace-agents/${agent.id}/status`, { status: next }, { _suppressToast: true });
      toast.success(tf('mpAgents.statusChanged', "Agent holati o'zgartirildi"));
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || tf('mpAgents.statusError', "Holatni o'zgartirib bo'lmadi"));
    }
  };

  const openBalance = async (agent) => {
    try {
      const { data } = await api.get(`/marketplace-agents/${agent.id}/balance`, { _suppressToast: true });
      setBalanceView({ agent, data });
    } catch (e) {
      toast.error(e.response?.data?.detail || tf('mpAgents.loadError', "Ma'lumotni yuklab bo'lmadi"));
    }
  };

  const openPayout = async (agent) => {
    setPayAgent(agent);
    setPayError('');
    setPayForm({ amount: agent.balance > 0 ? String(agent.balance) : '', wallet_id: '', payment_type: 'cash', note: '' });
    try {
      const { data } = await api.get('/finance/wallets', { _suppressToast: true });
      const list = (Array.isArray(data) ? data : []).filter(w => w.is_active !== false);
      setWallets(list);
      if (list.length === 1) setPayForm(f => ({ ...f, wallet_id: String(list[0].id) }));
    } catch {
      setWallets([]);
    }
  };

  const submitPayout = async (e) => {
    e.preventDefault();
    if (!payAgent || paying) return;
    if (!payForm.wallet_id) { setPayError(tf('mpAgents.pickWallet', 'Kassani tanlang')); return; }
    if (!(Number(payForm.amount) > 0)) { setPayError(tf('mpAgents.enterAmount', "To'lov summasini kiriting")); return; }
    setPaying(true);
    setPayError('');
    try {
      await api.post(`/marketplace-agents/${payAgent.id}/payouts`, {
        amount: Number(payForm.amount),
        wallet_id: Number(payForm.wallet_id),
        payment_type: payForm.payment_type,
        note: payForm.note.trim() || null,
      }, { _suppressToast: true });
      toast.success(tf('mpAgents.paid', "To'lov kassadan amalga oshirildi"));
      setPayAgent(null);
      load();
    } catch (err) {
      const d = err.response?.data?.detail;
      setPayError(typeof d === 'string' ? d : tf('mpAgents.payError', "To'lovni amalga oshirib bo'lmadi"));
    } finally {
      setPaying(false);
    }
  };

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      <div className="mb-5">
        <h1 className="text-xl font-bold text-slate-800">{tf('mpAgents.title', 'Marketplace agentlari')}</h1>
        <p className="text-sm text-slate-500">{tf('mpAgents.subtitle', "Agentlar, ularning balansi va kassadan to'lovlar")}</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-2 mb-4">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={tf('mpAgents.search', 'Ism yoki telefon bo\'yicha qidirish')}
          className="flex-1 p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">{tf('mpAgents.allStatuses', 'Barcha holatlar')}</option>
          <option value="active">{statusLabel('active')}</option>
          <option value="pending">{statusLabel('pending')}</option>
          <option value="blocked">{statusLabel('blocked')}</option>
        </select>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl overflow-x-auto">
        {loading ? (
          <div className="flex justify-center py-16"><div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" /></div>
        ) : items.length === 0 ? (
          <p className="text-center text-sm text-slate-400 py-16">{tf('mpAgents.empty', 'Agentlar topilmadi')}</p>
        ) : (
          <table className="w-full text-left">
            <thead className="bg-slate-50 text-xs text-slate-500 uppercase">
              <tr>
                <th className="px-4 py-3">{tf('mpAgents.colName', 'Agent')}</th>
                <th className="px-4 py-3">{tf('mpAgents.colPhone', 'Telefon')}</th>
                <th className="px-4 py-3">{tf('mpAgents.colStatus', 'Holati')}</th>
                <th className="px-4 py-3 text-right">{tf('mpAgents.colProducts', 'Tovarlar')}</th>
                <th className="px-4 py-3 text-right">{tf('mpAgents.colBalance', "Balans (so'm)")}</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map(a => (
                <tr key={a.id} className="hover:bg-slate-50/60">
                  <td className="px-4 py-3 text-sm font-semibold text-slate-800">{a.name}</td>
                  <td className="px-4 py-3 text-sm text-slate-600">{a.phone}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-semibold ${STATUS_STYLE[a.status] || 'bg-slate-100 text-slate-600'}`}>
                      {statusLabel(a.status)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-right text-slate-700">{a.products}</td>
                  <td className="px-4 py-3 text-sm text-right font-bold text-slate-800">{fmt(a.balance)}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap justify-end gap-1.5">
                      <button onClick={() => openBalance(a)} className="px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg">
                        {tf('mpAgents.balance', 'Balans')}
                      </button>
                      <button
                        onClick={() => openPayout(a)}
                        disabled={!(a.balance > 0)}
                        className="px-2.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-lg disabled:opacity-40"
                      >
                        {tf('mpAgents.payout', "To'lov qilish")}
                      </button>
                      {a.status !== 'active' && (
                        <button onClick={() => changeStatus(a, 'active')} className="px-2.5 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200 text-xs font-semibold rounded-lg">
                          {tf('mpAgents.activate', 'Faollashtirish')}
                        </button>
                      )}
                      {a.status !== 'blocked' && (
                        <button onClick={() => changeStatus(a, 'blocked')} className="px-2.5 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 text-xs font-semibold rounded-lg">
                          {tf('mpAgents.block', 'Bloklash')}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Balans */}
      {balanceView && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4" onClick={() => setBalanceView(null)}>
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-slate-800 mb-3">{balanceView.agent.name}</h3>
            <dl className="text-sm divide-y divide-slate-100">
              {[
                ['mpAgents.sales', 'Sotuvlar', balanceView.data.sales],
                ['mpAgents.commission', 'Komissiya', balanceView.data.commission],
                ['mpAgents.refunds', 'Qaytarishlar', balanceView.data.refunds],
                ['mpAgents.paidOut', "To'langan", balanceView.data.paid_out],
                ['mpAgents.colBalance', "Balans (so'm)", balanceView.data.balance],
                ['mpAgents.warehouseDebt', 'Ombordagi tovar qarzi', balanceView.data.warehouse_debt],
              ].map(([k, fb, v]) => (
                <div key={k} className="flex justify-between py-2">
                  <dt className="text-slate-500">{tf(k, fb)}</dt>
                  <dd className="font-semibold text-slate-800">{fmt(v)}</dd>
                </div>
              ))}
            </dl>
            <div className="flex justify-end mt-4">
              <button onClick={() => setBalanceView(null)} className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-semibold rounded-xl">
                {tf('mpAgents.close', 'Yopish')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* To'lov */}
      {payAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <form onSubmit={submitPayout} className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl">
            <h3 className="text-lg font-bold text-slate-800 mb-1">{tf('mpAgents.payoutTitle', "Agentga to'lov")}</h3>
            <p className="text-xs text-slate-500 mb-4">
              {payAgent.name} — {tf('mpAgents.colBalance', "Balans (so'm)")}: {fmt(payAgent.balance)}
            </p>

            {payError && <div className="px-3 py-2 mb-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl">{payError}</div>}

            <label className="block mb-3">
              <span className="block text-xs font-semibold text-slate-600 mb-1">{tf('mpAgents.amount', "Summa (so'm)")}</span>
              <input
                type="number" min="0" step="0.01" value={payForm.amount}
                onChange={(e) => setPayForm(f => ({ ...f, amount: e.target.value }))}
                className="w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </label>

            <label className="block mb-3">
              <span className="block text-xs font-semibold text-slate-600 mb-1">{tf('mpAgents.wallet', 'Kassa')}</span>
              <select
                value={payForm.wallet_id}
                onChange={(e) => setPayForm(f => ({ ...f, wallet_id: e.target.value }))}
                className="w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              >
                <option value="">{tf('mpAgents.selectWallet', 'Kassani tanlang')}</option>
                {wallets.map(w => (
                  <option key={w.id} value={w.id}>{w.name}{w.balance !== undefined ? ` — ${fmt(w.balance)}` : ''}</option>
                ))}
              </select>
            </label>

            <label className="block mb-3">
              <span className="block text-xs font-semibold text-slate-600 mb-1">{tf('mpAgents.paymentType', "To'lov turi")}</span>
              <select
                value={payForm.payment_type}
                onChange={(e) => setPayForm(f => ({ ...f, payment_type: e.target.value }))}
                className="w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              >
                <option value="cash">{tf('mpAgents.cash', 'Naqd')}</option>
                <option value="card">{tf('mpAgents.card', 'Karta')}</option>
              </select>
            </label>

            <label className="block mb-4">
              <span className="block text-xs font-semibold text-slate-600 mb-1">{tf('mpAgents.note', 'Izoh')}</span>
              <input
                value={payForm.note} maxLength={300}
                onChange={(e) => setPayForm(f => ({ ...f, note: e.target.value }))}
                className="w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </label>

            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setPayAgent(null)} className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-semibold rounded-xl">
                {tf('mpAgents.cancel', 'Bekor qilish')}
              </button>
              <button type="submit" disabled={paying} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-xl disabled:opacity-50">
                {tf('mpAgents.pay', "To'lash")}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
