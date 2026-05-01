import { useState } from 'react';
import api from '../api/axios';
import toast from 'react-hot-toast';

export default function ShiftOpenModal({ onOpened, onCancel }) {
  const [cash, setCash] = useState('');
  const [saving, setSaving] = useState(false);

  const handleOpen = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post('/shifts/open', { opening_cash: Number(cash) || 0 });
      toast.success('Smena muvaffaqiyatli ochildi!');
      onOpened();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Xatolik yuz berdi');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
        <div className="p-6 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-amber-100 rounded-xl flex items-center justify-center shrink-0">
              <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <h3 className="font-bold text-slate-800">Smena ochilmagan</h3>
              <p className="text-xs text-slate-500">To'lov qilish uchun avval smenani oching</p>
            </div>
          </div>
        </div>
        <form onSubmit={handleOpen} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">
              Boshlang'ich kassadagi pul (so'm)
            </label>
            <input
              type="number" min="0" autoFocus value={cash}
              onChange={e => setCash(e.target.value)}
              placeholder="0"
              className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>
          <div className="flex gap-3">
            {onCancel && (
              <button type="button" onClick={onCancel}
                className="flex-1 py-2.5 border border-slate-200 text-slate-600 font-medium text-sm rounded-xl hover:bg-slate-50 transition-colors">
                Bekor
              </button>
            )}
            <button type="submit" disabled={saving}
              className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-semibold text-sm rounded-xl transition-colors">
              {saving ? '...' : '✓ Smenani ochish'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
