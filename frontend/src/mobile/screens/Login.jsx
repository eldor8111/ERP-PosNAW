import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { useLang } from '../../context/LangContext';
import { useMobileAuth } from '../lib/authContext';
import { errText } from '../lib/api';
import { Btn } from '../ui';
import { inputCls } from '../format';

export default function Login() {
  const { t, lang, setLang, LANGUAGES } = useLang();
  const { login } = useMobileAuth();
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError('');
    const digits = phone.replace(/\D/g, '');
    try {
      await login(digits.length === 9 ? `998${digits}` : digits, password);
    } catch (err) {
      setError(errText(err, t('m.loginError')));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-full flex flex-col px-6 pt-16 pb-8 bg-bg-base">
      <div className="flex justify-end gap-1">
        {LANGUAGES.map(l => (
          <button key={l.code} onClick={() => setLang(l.code)}
            className={`px-2.5 py-1 rounded-lg text-xs font-bold ${lang === l.code ? 'bg-brand text-white' : 'text-ink-500'}`}>
            {l.code.toUpperCase()}
          </button>
        ))}
      </div>
      <div className="mt-10 mb-10 text-center">
        <img src="./ecode-logo-icon.png" alt="" className="w-16 h-16 mx-auto rounded-2xl" />
        <h1 className="mt-4 text-2xl font-bold text-ink-900">E-code Mobile</h1>
        <p className="mt-1 text-sm text-ink-500">{t('m.loginSubtitle')}</p>
      </div>
      <form onSubmit={submit} className="space-y-3">
        <div className="flex items-center rounded-xl border border-line bg-surface focus-within:ring-2 focus-within:ring-brand/40">
          <span className="pl-4 pr-2 text-ink-500 text-[15px]">+998</span>
          <input value={phone} onChange={e => setPhone(e.target.value)} inputMode="tel" autoComplete="tel"
            placeholder="90 123 45 67" required className="flex-1 min-h-12 pr-4 bg-transparent outline-none text-[15px]" />
        </div>
        <div className="relative">
          <input type={show ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)}
            placeholder={t('m.password')} required autoComplete="current-password" className={`${inputCls} pr-12`} />
          <button type="button" onClick={() => setShow(s => !s)} className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-ink-300">
            {show ? <EyeOff className="size-5" /> : <Eye className="size-5" />}
          </button>
        </div>
        {error && <div className="text-sm text-danger bg-danger/10 rounded-xl px-4 py-3">{error}</div>}
        <Btn type="submit" loading={busy} className="w-full">{t('m.signIn')}</Btn>
      </form>
      <p className="mt-auto pt-10 text-center text-xs text-ink-300">{t('m.loginHint')}</p>
    </div>
  );
}
