import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';

export default function PosLogin() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({ phone: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPass, setShowPass] = useState(false);
  const [showServerModal, setShowServerModal] = useState(false);
  const [serverUrlInput, setServerUrlInput] = useState(
    () => localStorage.getItem('api_server_url') || 'http://localhost:8000/api'
  );

  // Korxona tanlash state
  const [companies, setCompanies] = useState(null); // null = yo'q, [] = ro'yxat

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const user = await login(form.phone, form.password);

      // Agar foydalanuvchi bir nechta korxonaga ulangan bo'lsa
      if (user?.companies && user.companies.length > 1) {
        // Korxona tanlash ekranini ko'rsat
        setCompanies(user.companies);
      } else {
        navigate('/admin/pos-desktop');
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Telefon yoki parol noto'g'ri");
    } finally {
      setLoading(false);
    }
  };

  const selectCompany = async (company) => {
    setLoading(true);
    try {
      // Korxonani aktiv qilib belgilash
      await api.post('/auth/select-company', { company_id: company.id });
      navigate('/admin/pos-desktop');
    } catch {
      // Agar endpoint yo'q bo'lsa ham POS ga o'tishni davom ettir
      localStorage.setItem('active_company_id', company.id);
      navigate('/admin/pos-desktop');
    } finally {
      setLoading(false);
    }
  };

  // ── Korxona tanlash ekrani ─────────────────────────────────────────────
  if (companies) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="text-center mb-10">
            <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-xl shadow-blue-500/30">
              <span className="text-white font-black text-xl tracking-tight">UBT</span>
            </div>
            <h1 className="text-2xl font-black text-white mb-2">Korxonani tanlang</h1>
            <p className="text-slate-400 text-sm">Qaysi korxona bilan ishlashni tanlang</p>
          </div>

          <div className="space-y-3">
            {companies.map((company) => (
              <button
                key={company.id}
                onClick={() => selectCompany(company)}
                disabled={loading}
                className="w-full bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-blue-500 rounded-2xl p-5 flex items-center gap-4 text-left transition-all group disabled:opacity-50"
              >
                <div className="w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center text-white font-black text-lg shrink-0 group-hover:scale-105 transition-transform shadow-lg shadow-blue-500/20">
                  {company.name?.slice(0, 1)?.toUpperCase() || 'K'}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-white font-bold text-base truncate">{company.name}</div>
                  {company.address && <div className="text-slate-400 text-sm mt-0.5 truncate">📍 {company.address}</div>}
                </div>
                <svg className="w-5 h-5 text-slate-500 group-hover:text-blue-400 transition-colors shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            ))}
          </div>

          <button
            onClick={() => setCompanies(null)}
            className="mt-6 w-full text-slate-500 hover:text-slate-300 text-sm font-medium transition-colors py-2"
          >
            ← Boshqa hisob bilan kirish
          </button>
        </div>
      </div>
    );
  }

  // ── Login ekrani ───────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="text-center mb-10">
          <div className="w-20 h-20 bg-linear-to-br from-blue-500 to-indigo-600 rounded-[28px] flex items-center justify-center mx-auto mb-5 shadow-2xl shadow-blue-500/30">
            <span className="text-white font-black text-2xl tracking-tight">UBT</span>
          </div>
          <h1 className="text-2xl font-black text-white mb-2">Kassaga kirish</h1>
          <p className="text-slate-400 text-sm">Hisob ma'lumotlarini kiriting</p>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2.5 bg-red-950/60 border border-red-800 text-red-400 rounded-2xl px-4 py-3 mb-5 text-sm">
            <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Phone */}
          <div>
            <label className="block text-sm font-semibold text-slate-300 mb-2">Telefon raqam</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none text-slate-500">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                </svg>
              </div>
              <input
                type="text"
                placeholder="998901234567"
                value={form.phone}
                onChange={e => setForm({ ...form, phone: e.target.value })}
                required
                className="w-full pl-11 pr-4 py-3.5 bg-slate-800 border border-slate-700 rounded-2xl text-white text-sm placeholder-slate-500
                  focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all"
              />
            </div>
          </div>

          {/* Password */}
          <div>
            <label className="block text-sm font-semibold text-slate-300 mb-2">Parol</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none text-slate-500">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
              <input
                type={showPass ? 'text' : 'password'}
                placeholder="••••••••"
                value={form.password}
                onChange={e => setForm({ ...form, password: e.target.value })}
                required
                className="w-full pl-11 pr-11 py-3.5 bg-slate-800 border border-slate-700 rounded-2xl text-white text-sm placeholder-slate-500
                  focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPass(!showPass)}
                className="absolute inset-y-0 right-4 flex items-center text-slate-500 hover:text-slate-300 transition-colors"
              >
                {showPass
                  ? <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" /></svg>
                  : <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15 12a3 3 0 11-6 0 3 3 0 016 0zM2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
                }
              </button>
            </div>
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3.5 rounded-2xl bg-linear-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700
              disabled:opacity-50 text-white font-bold text-sm transition-all shadow-lg shadow-blue-500/25
              flex items-center justify-center gap-2 mt-2"
          >
            {loading ? (
              <>
                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Kirish...
              </>
            ) : (
              <>
                Kassani ochish
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </>
            )}
          </button>
        </form>

        <p className="text-center text-slate-600 text-xs mt-8">
          Admin panel uchun{' '}
          <a href="/login" className="text-blue-500 hover:text-blue-400 font-medium transition-colors">
            oddiy kirish
          </a>
        </p>

        <p className="text-center text-slate-500 text-xs mt-3">
           <button
             type="button"
             onClick={() => setShowServerModal(true)}
             className="hover:underline text-slate-400"
           >
             🌐 Server Sozlamalari (IP)
           </button>
        </p>

        {/* Server URL Modal */}
        {showServerModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl w-full max-w-sm p-6">
              <h3 className="text-white font-bold text-lg mb-1">🌐 Server Sozlamalari</h3>
              <p className="text-slate-400 text-sm mb-4">Backend API manzilini kiriting</p>
              <input
                type="text"
                value={serverUrlInput}
                onChange={e => setServerUrlInput(e.target.value)}
                placeholder="http://localhost:8000/api"
                className="w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-xl text-white text-sm
                  placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 mb-4"
              />
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setShowServerModal(false)}
                  className="flex-1 py-2.5 rounded-xl border border-slate-600 text-slate-300 hover:bg-slate-700 text-sm font-semibold transition-colors"
                >
                  Bekor
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const trimmed = serverUrlInput.trim();
                    if (trimmed) {
                      localStorage.setItem('api_server_url', trimmed);
                      setShowServerModal(false);
                      window.location.reload();
                    }
                  }}
                  className="flex-1 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition-colors"
                >
                  Saqlash
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
