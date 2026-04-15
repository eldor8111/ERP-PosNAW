import { useState, useEffect } from 'react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import toast from 'react-hot-toast';

const fmtDate = (s) => s ? new Date(s).toLocaleString('ru-RU', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit' }).replace(',','') : '—';

export default function Warehouse() {
  const { t } = useLang();
  const [warehouses, setWarehouses] = useState([]);
  const [branches, setBranches]     = useState([]);
  const [loading, setLoading]       = useState(true);
  const [modal, setModal]           = useState(null); // null | { mode:'create' } | { mode:'edit', wh }
  const [name, setName]             = useState('');
  const [branchId, setBranchId]     = useState('');
  const [saving, setSaving]         = useState(false);
  const [err, setErr]               = useState('');
  const [delConfirm, setDelConfirm] = useState(null); // wh object

  const load = async () => {
    setLoading(true);
    try { const { data } = await api.get('/warehouses'); setWarehouses(data); }
    catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    load();
    api.get('/branches').then(r => setBranches(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
  }, []);

  const openCreate = () => { setName(''); setBranchId(''); setErr(''); setModal({ mode:'create' }); };
  const openEdit   = (wh) => { setName(wh.name); setBranchId(wh.branch_id ?? ''); setErr(''); setModal({ mode:'edit', wh }); };
  const closeModal = () => { setModal(null); setErr(''); };

  const remove = async () => {
    try {
      await api.delete(`/warehouses/${delConfirm.id}`);
      setDelConfirm(null);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || 'Xatolik yuz berdi');
    }
  };

  const save = async () => {
    if (!name.trim()) { setErr("Nomi bo'sh bo'lmasin"); return; }
    setSaving(true); setErr('');
    try {
      const payload = { name: name.trim(), branch_id: branchId ? Number(branchId) : null };
      if (modal.mode === 'create') {
        await api.post('/warehouses', payload);
      } else {
        await api.patch(`/warehouses/${modal.wh.id}`, payload);
      }
      closeModal();
      load();
    } catch (e) {
      setErr(e.response?.data?.detail || 'Xatolik yuz berdi');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-slate-700">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          <span className="text-base font-semibold">{t('warehouse.title')}</span>
        </div>
        <button
          onClick={openCreate}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {t('warehouse.newTransfer')}
        </button>
      </div>

      {/* Table */}
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="w-7 h-7 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <table className="min-w-full">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase w-12">#</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">{t('common.name')}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">{t('common.branch') || 'Filial'}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase">{t('common.date')}</th>
                <th className="px-4 py-3 w-24" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {warehouses.map((wh, i) => (
                <tr key={wh.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 text-sm text-slate-500">{i + 1}</td>
                  <td className="px-4 py-3 text-sm text-slate-800 font-medium">{wh.name}</td>
                  <td className="px-4 py-3 text-sm text-slate-500">
                    {wh.branch_id ? (branches.find(b => b.id === wh.branch_id)?.name || '—') : '—'}
                  </td>
                  <td className="px-4 py-3 text-sm text-slate-500">{fmtDate(wh.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => openEdit(wh)}
                        className="p-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors"
                        title="Tahrirlash"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                            d="M15.232 5.232l3.536 3.536M9 13l6.5-6.5a2 2 0 012.828 0l.172.172a2 2 0 010 2.828L12 16H9v-3z" />
                        </svg>
                      </button>
                      <button
                        onClick={() => setDelConfirm(wh)}
                        className="p-1.5 bg-red-500 hover:bg-red-600 text-white rounded transition-colors"
                        title="O'chirish"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {warehouses.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-12 text-center text-sm text-slate-400">
                    {t('warehouse.noStocks')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Delete confirm */}
      {delConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-sm">
            <div className="px-6 py-5">
              <h3 className="text-base font-semibold text-slate-800 mb-2">{t('confirm.delete')}</h3>
              <p className="text-sm text-slate-500">
                <span className="font-medium text-slate-700">"{delConfirm.name}"</span> omborini o'chirishni xohlaysizmi?
              </p>
            </div>
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-200">
              <button
                onClick={() => setDelConfirm(null)}
                className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={remove}
                className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white text-sm font-semibold rounded-lg transition-colors"
              >
                {t('common.delete')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal */}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
              <h3 className="text-base font-semibold text-slate-800">
                {modal.mode === 'create' ? t('warehouse.newTransfer') : t('common.edit')}
              </h3>
              <button onClick={closeModal} className="text-slate-400 hover:text-slate-600 transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Modal body */}
            <div className="px-6 py-5">
              <input
                autoFocus
                placeholder="Nomi"
                value={name}
                onChange={e => setName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && save()}
                className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {branches.length > 0 && (
                <div className="mt-3">
                  <label className="block text-xs font-semibold text-slate-500 mb-1">{t('common.branch') || 'Filial'} (ixtiyoriy)</label>
                  <select
                    value={branchId}
                    onChange={e => setBranchId(e.target.value)}
                    className="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">— Filialsiz —</option>
                    {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </div>
              )}
              {err && <p className="mt-2 text-sm text-red-500">{err}</p>}
            </div>

            {/* Modal footer */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-200">
              <button
                onClick={closeModal}
                className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={save}
                disabled={saving}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                </svg>
                {saving ? t('common.saving') : t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
