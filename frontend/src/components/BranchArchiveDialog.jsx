// T1.12: Filialni yopish (arxivlash) dialogi.
// - ochilganda GET /branches/{id}/close-check — to'sqinlik qiluvchi narsalar (ochiq smena, qoldiq, kassa balansi...) soni
// - sabab (reason) va xodimlarni boshqa filialga ko'chirish (select)
// - blokerlar bo'lsa "Yopish" tugmasi o'chiq; aks holda POST /branches/{id}/archive
// Props: branch {id,name}, branches (barcha filiallar ro'yxati; faqat faollari ko'chirish uchun taklif qilinadi),
//        onClose(), onArchived(branch)
import { useState, useEffect, useMemo } from 'react';
import api from '../api/axios';
import toast from 'react-hot-toast';
import { useLang } from '../context/LangContext';

// i18n fayllarida kalit hali bo'lmasa ham dialog to'g'ri matn ko'rsatadi (t() kalitning o'zini qaytaradi)
const FALLBACK = {
  uz: {
    'branch.closeCheckTitle': 'Filialni yopish',
    'branch.closeCheckInfo': '"{name}" filiali yopiladi. Yopilgan filialda sotuv, smena va kassa amallari to\'xtaydi.',
    'branch.closeCheckChecking': 'Tekshirilmoqda...',
    'branch.closeCheckBlocked': 'Filialni hozir yopib bo\'lmaydi. Avval quyidagilarni hal qiling:',
    'branch.closeCheckOk': 'To\'sqinlik yo\'q — filialni yopish mumkin.',
    'branch.blockers.open_shifts': 'Ochiq smenalar',
    'branch.blockers.open_kassa': 'Ochiq kassalar',
    'branch.blockers.wallets_with_balance': 'Balansi bor kassalar',
    'branch.blockers.stock': 'Qoldiqli omborlar',
    'branch.blockers.active_users': 'Faol xodimlar',
    'branch.blockers.open_orders': 'Ochiq buyurtmalar',
    'branch.blockers.pending_transfers': 'Kutilayotgan ko\'chirishlar',
    'branch.blockers.open_counts': 'Ochiq inventarizatsiyalar',
    'branch.blockers.open_production': 'Ochiq ishlab chiqarish',
    'branch.blockers.open_purchase_orders': 'Ochiq xarid buyurtmalari',
    'branch.blockers.pending_sales': 'Kutilayotgan sotuvlar',
    'branch.reason': 'Yopish sababi',
    'branch.reasonPlaceholder': 'Masalan: ijara muddati tugadi',
    'branch.reassignUsers': 'Xodimlarni ko\'chirish',
    'branch.reassignNone': '— ko\'chirmaslik —',
    'branch.archiveConfirm': 'Yopish',
    'branch.cancel': 'Bekor qilish',
    'branch.archived': 'Filial yopildi',
  },
  ru: {
    'branch.closeCheckTitle': 'Закрытие филиала',
    'branch.closeCheckInfo': 'Филиал "{name}" будет закрыт. В закрытом филиале продажи, смены и операции с кассой остановятся.',
    'branch.closeCheckChecking': 'Проверка...',
    'branch.closeCheckBlocked': 'Сейчас филиал закрыть нельзя. Сначала решите следующее:',
    'branch.closeCheckOk': 'Препятствий нет — филиал можно закрыть.',
    'branch.blockers.open_shifts': 'Открытые смены',
    'branch.blockers.open_kassa': 'Открытые кассы',
    'branch.blockers.wallets_with_balance': 'Кассы с остатком',
    'branch.blockers.stock': 'Склады с остатками',
    'branch.blockers.active_users': 'Активные сотрудники',
    'branch.blockers.open_orders': 'Открытые заказы',
    'branch.blockers.pending_transfers': 'Ожидающие перемещения',
    'branch.blockers.open_counts': 'Открытые инвентаризации',
    'branch.blockers.open_production': 'Открытое производство',
    'branch.blockers.open_purchase_orders': 'Открытые заказы поставщикам',
    'branch.blockers.pending_sales': 'Ожидающие продажи',
    'branch.reason': 'Причина закрытия',
    'branch.reasonPlaceholder': 'Например: истёк срок аренды',
    'branch.reassignUsers': 'Перевести сотрудников',
    'branch.reassignNone': '— не переводить —',
    'branch.archiveConfirm': 'Закрыть',
    'branch.cancel': 'Отмена',
    'branch.archived': 'Филиал закрыт',
  },
  en: {
    'branch.closeCheckTitle': 'Close branch',
    'branch.closeCheckInfo': 'Branch "{name}" will be closed. Sales, shifts and cash operations stop in a closed branch.',
    'branch.closeCheckChecking': 'Checking...',
    'branch.closeCheckBlocked': 'The branch cannot be closed yet. Resolve the following first:',
    'branch.closeCheckOk': 'Nothing blocks closing — the branch can be closed.',
    'branch.blockers.open_shifts': 'Open shifts',
    'branch.blockers.open_kassa': 'Open cash registers',
    'branch.blockers.wallets_with_balance': 'Cash registers with balance',
    'branch.blockers.stock': 'Warehouses with stock',
    'branch.blockers.active_users': 'Active staff',
    'branch.blockers.open_orders': 'Open orders',
    'branch.blockers.pending_transfers': 'Pending transfers',
    'branch.blockers.open_counts': 'Open stock counts',
    'branch.blockers.open_production': 'Open production orders',
    'branch.blockers.open_purchase_orders': 'Open purchase orders',
    'branch.blockers.pending_sales': 'Pending sales',
    'branch.reason': 'Reason for closing',
    'branch.reasonPlaceholder': 'For example: lease ended',
    'branch.reassignUsers': 'Move staff to',
    'branch.reassignNone': '— do not move —',
    'branch.archiveConfirm': 'Close',
    'branch.cancel': 'Cancel',
    'branch.archived': 'Branch closed',
  },
};

const BLOCKER_KEYS = [
  'open_shifts', 'open_kassa', 'wallets_with_balance', 'stock', 'active_users', 'open_orders',
  'pending_transfers', 'open_counts', 'open_production', 'open_purchase_orders', 'pending_sales',
];

const blockerCount = (v) => (Array.isArray(v) ? v.length : Number(v) || 0);

export default function BranchArchiveDialog({ branch, branches = [], onClose, onArchived }) {
  const { t, lang } = useLang();
  const [check, setCheck] = useState(null);       // { can_close, blockers } | null (yuklanmoqda)
  const [checkError, setCheckError] = useState('');
  const [reason, setReason] = useState('');
  const [reassignTo, setReassignTo] = useState('');
  const [saving, setSaving] = useState(false);

  // t(kalit) i18n da topilmasa kalitning o'zini qaytaradi -> lokal zaxira matn
  const tr = (key, vars) => {
    const v = t(key, vars);
    if (v !== key) return v;
    let s = (FALLBACK[lang] || FALLBACK.uz)[key] ?? FALLBACK.uz[key] ?? key;
    if (vars) Object.entries(vars).forEach(([k, val]) => { s = s.replace(`{${k}}`, val ?? ''); });
    return s;
  };

  // Ko'chirish uchun faqat boshqa FAOL filiallar
  const targets = useMemo(
    () => (branches || []).filter(b => b.id !== branch?.id && b.is_active !== false),
    [branches, branch?.id],
  );

  useEffect(() => {
    if (!branch?.id) return undefined;
    let cancelled = false;
    setCheck(null);
    setCheckError('');
    const params = reassignTo ? { reassign_users_to_branch_id: Number(reassignTo) } : {};
    api.get(`/branches/${branch.id}/close-check`, { params })
      .then(r => { if (!cancelled) setCheck(r.data); })
      .catch(err => { if (!cancelled) setCheckError(err.response?.data?.detail || 'Xatolik yuz berdi'); });
    return () => { cancelled = true; };
  }, [branch?.id, reassignTo]);

  const blockers = check?.blockers || {};
  const activeBlockers = BLOCKER_KEYS.filter(k => blockerCount(blockers[k]) > 0);
  const canClose = !!check?.can_close;

  const handleArchive = async () => {
    setSaving(true);
    try {
      const payload = { reason: reason.trim() || null };
      if (reassignTo) payload.reassign_users_to_branch_id = Number(reassignTo);
      const r = await api.post(`/branches/${branch.id}/archive`, payload);
      toast.success(tr('branch.archived'));
      onArchived?.(r.data);
    } catch (err) {
      // 409: detail — sabablar matni (blokerlar o'zgargan bo'lishi mumkin), qayta tekshiramiz
      toast.error(err.response?.data?.detail || 'Xatolik yuz berdi');
      if (err.response?.data?.blockers) {
        setCheck({ can_close: false, blockers: err.response.data.blockers });
      }
    } finally {
      setSaving(false);
    }
  };

  if (!branch) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-slate-100">
          <h3 className="text-lg font-bold text-slate-800">{tr('branch.closeCheckTitle')}</h3>
          <p className="text-sm text-slate-500 mt-1">{tr('branch.closeCheckInfo', { name: branch.name })}</p>
        </div>

        <div className="p-6 space-y-4">
          {checkError && <p className="text-sm text-red-600">{checkError}</p>}
          {!check && !checkError && <p className="text-sm text-slate-400">{tr('branch.closeCheckChecking')}</p>}

          {check && !canClose && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
              <p className="text-sm font-semibold text-amber-800 mb-2">{tr('branch.closeCheckBlocked')}</p>
              <ul className="space-y-1 text-sm text-amber-900">
                {activeBlockers.map(k => (
                  <li key={k} className="flex justify-between gap-3">
                    <span>{tr(`branch.blockers.${k}`)}</span>
                    <span className="font-bold">{blockerCount(blockers[k])}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {check && canClose && (
            <p className="text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl p-3">
              {tr('branch.closeCheckOk')}
            </p>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">{tr('branch.reason')}</label>
            <input
              type="text"
              maxLength={255}
              value={reason}
              onChange={e => setReason(e.target.value)}
              placeholder={tr('branch.reasonPlaceholder')}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-200"
            />
          </div>

          {targets.length > 0 && (
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">{tr('branch.reassignUsers')}</label>
              <select
                value={reassignTo}
                onChange={e => setReassignTo(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-red-200"
              >
                <option value="">{tr('branch.reassignNone')}</option>
                {targets.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </div>
          )}
        </div>

        <div className="p-6 pt-0 flex gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            {tr('branch.cancel')}
          </button>
          <button
            type="button"
            onClick={handleArchive}
            disabled={!canClose || saving}
            className="flex-1 px-4 py-2.5 rounded-xl bg-red-600 text-white text-sm font-bold hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {tr('branch.archiveConfirm')}
          </button>
        </div>
      </div>
    </div>
  );
}
