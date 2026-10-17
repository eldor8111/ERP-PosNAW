import { useState, useEffect, useCallback } from 'react';
import api from '../../api/axios';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LangContext';
import toast from 'react-hot-toast';

// T1.19: Audit jurnali sahifasi (GET /audit-logs). Faqat admin/director (+ super_admin).
// Matnlar: i18n da 'audit.*' kaliti bo'lsa — t(), bo'lmasa quyidagi mahalliy lug'at (uz/ru/en).
const LOCAL = {
  uz: {
    title: 'Audit jurnali', subtitle: 'Kim, qachon va nimani o\'zgartirgani',
    date_from: 'Sanadan', date_to: 'Sanagacha', user: 'Foydalanuvchi', action: 'Amal',
    branch: 'Filial', entity_type: 'Ob\'ekt turi', entity_id: 'Ob\'ekt ID', company: 'Korxona ID',
    all: 'Barchasi', search: 'Qidirish', reset: 'Tozalash', time: 'Vaqt', entity: 'Ob\'ekt',
    ip: 'IP', details: 'Tafsilot', total: 'Jami', empty: 'Yozuvlar topilmadi', loading: 'Yuklanmoqda...',
    prev: 'Oldingi', next: 'Keyingi', field: 'Maydon', old: 'Eski qiymat', new: 'Yangi qiymat',
    no_changes: 'Qiymatlar yo\'q', load_error: 'Audit jurnalini yuklab bo\'lmadi', page: 'Sahifa',
  },
  ru: {
    title: 'Журнал аудита', subtitle: 'Кто, когда и что изменил',
    date_from: 'С даты', date_to: 'По дату', user: 'Пользователь', action: 'Действие',
    branch: 'Филиал', entity_type: 'Тип объекта', entity_id: 'ID объекта', company: 'ID компании',
    all: 'Все', search: 'Найти', reset: 'Сбросить', time: 'Время', entity: 'Объект',
    ip: 'IP', details: 'Детали', total: 'Всего', empty: 'Записи не найдены', loading: 'Загрузка...',
    prev: 'Назад', next: 'Далее', field: 'Поле', old: 'Старое значение', new: 'Новое значение',
    no_changes: 'Нет значений', load_error: 'Не удалось загрузить журнал аудита', page: 'Страница',
  },
  en: {
    title: 'Audit log', subtitle: 'Who changed what and when',
    date_from: 'From', date_to: 'To', user: 'User', action: 'Action',
    branch: 'Branch', entity_type: 'Entity type', entity_id: 'Entity ID', company: 'Company ID',
    all: 'All', search: 'Search', reset: 'Reset', time: 'Time', entity: 'Entity',
    ip: 'IP', details: 'Details', total: 'Total', empty: 'No records found', loading: 'Loading...',
    prev: 'Previous', next: 'Next', field: 'Field', old: 'Old value', new: 'New value',
    no_changes: 'No values', load_error: 'Failed to load audit log', page: 'Page',
  },
};

// Backendda ishlatiladigan asosiy entity_type lar (filtr uchun)
const ENTITY_TYPES = [
  'stock_transfer', 'inventory_count', 'stock', 'chiqim', 'stock_movement', 'warehouse', 'branch',
  'production_order', 'expense', 'transaction', 'wallet', 'shift', 'customer', 'sale', 'product',
  'supplier', 'purchase_order', 'user',
];

const PAGE_SIZE = 50;

const fmtDt = (dt) => {
  if (!dt) return '—';
  return new Date(dt).toLocaleString('uz-UZ', {
    day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
};

const fmtVal = (v) => {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
};

// old/new farqi: barcha kalitlar birlashmasi, o'zgarganlari belgilanadi
function diffRows(oldV, newV) {
  const o = oldV && typeof oldV === 'object' ? oldV : {};
  const n = newV && typeof newV === 'object' ? newV : {};
  const keys = Array.from(new Set([...Object.keys(o), ...Object.keys(n)]));
  return keys.map((k) => ({
    key: k, oldVal: o[k], newVal: n[k],
    changed: JSON.stringify(o[k] ?? null) !== JSON.stringify(n[k] ?? null),
  }));
}

const EMPTY_FILTERS = { date_from: '', date_to: '', user_id: '', action: '', branch_id: '', entity_type: '', entity_id: '', company_id: '' };

export default function AuditLogs() {
  const { user } = useAuth();
  const { t, lang } = useLang();
  const tr = useCallback((k) => {
    const v = t('audit.' + k);
    return v === 'audit.' + k ? ((LOCAL[lang] || LOCAL.uz)[k] ?? LOCAL.uz[k] ?? k) : v;
  }, [t, lang]);

  const isSuper = user?.role === 'super_admin';
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [applied, setApplied] = useState(EMPTY_FILTERS);
  const [page, setPage] = useState(0);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(null);
  const [users, setUsers] = useState([]);
  const [branches, setBranches] = useState([]);

  useEffect(() => {
    api.get('/branches').then((r) => setBranches(Array.isArray(r.data) ? r.data : [])).catch(() => {});
    api.get('/users/').then((r) => {
      const d = r.data;
      setUsers(Array.isArray(d) ? d : (Array.isArray(d?.items) ? d.items : []));
    }).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { skip: page * PAGE_SIZE, limit: PAGE_SIZE };
      Object.entries(applied).forEach(([k, v]) => { if (v !== '' && v !== null) params[k] = v; });
      const { data } = await api.get('/audit-logs', { params });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      toast.error(err?.response?.data?.detail || tr('load_error'));
    } finally {
      setLoading(false);
    }
  }, [applied, page, tr]);

  useEffect(() => { load(); }, [load]);

  const onSearch = (e) => { e.preventDefault(); setPage(0); setExpanded(null); setApplied(filters); };
  const onReset = () => { setFilters(EMPTY_FILTERS); setApplied(EMPTY_FILTERS); setPage(0); setExpanded(null); };
  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }));

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const inputCls = 'border border-gray-300 rounded-lg px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500';

  return (
    <div className="p-4 md:p-6 space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">{tr('title')}</h1>
        <p className="text-sm text-gray-500">{tr('subtitle')}</p>
      </div>

      <form onSubmit={onSearch} className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          <label className="text-xs text-gray-600">{tr('date_from')}
            <input type="date" className={inputCls} value={filters.date_from} onChange={set('date_from')} />
          </label>
          <label className="text-xs text-gray-600">{tr('date_to')}
            <input type="date" className={inputCls} value={filters.date_to} onChange={set('date_to')} />
          </label>
          <label className="text-xs text-gray-600">{tr('user')}
            <select className={inputCls} value={filters.user_id} onChange={set('user_id')}>
              <option value="">{tr('all')}</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.name || u.username || u.phone || u.id}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-600">{tr('action')}
            <input type="text" className={inputCls} placeholder="TRANSFER_CANCEL" value={filters.action}
              onChange={(e) => setFilters((f) => ({ ...f, action: e.target.value.toUpperCase() }))} />
          </label>
          <label className="text-xs text-gray-600">{tr('branch')}
            <select className={inputCls} value={filters.branch_id} onChange={set('branch_id')}>
              <option value="">{tr('all')}</option>
              {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-600">{tr('entity_type')}
            <select className={inputCls} value={filters.entity_type} onChange={set('entity_type')}>
              <option value="">{tr('all')}</option>
              {ENTITY_TYPES.map((e) => <option key={e} value={e}>{e}</option>)}
            </select>
          </label>
          <label className="text-xs text-gray-600">{tr('entity_id')}
            <input type="number" min="1" className={inputCls} value={filters.entity_id} onChange={set('entity_id')} />
          </label>
          {isSuper && (
            <label className="text-xs text-gray-600">{tr('company')}
              <input type="number" min="1" className={inputCls} value={filters.company_id} onChange={set('company_id')} />
            </label>
          )}
        </div>
        <div className="flex gap-2 mt-3">
          <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">{tr('search')}</button>
          <button type="button" onClick={onReset} className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200">{tr('reset')}</button>
          <span className="ml-auto text-sm text-gray-500 self-center">{tr('total')}: {total}</span>
        </div>
      </form>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 text-gray-600 text-left">
            <tr>
              <th className="px-3 py-2 w-8"></th>
              <th className="px-3 py-2">{tr('time')}</th>
              <th className="px-3 py-2">{tr('user')}</th>
              <th className="px-3 py-2">{tr('action')}</th>
              <th className="px-3 py-2">{tr('entity')}</th>
              <th className="px-3 py-2">{tr('branch')}</th>
              <th className="px-3 py-2">{tr('ip')}</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-gray-400">{tr('loading')}</td></tr>
            )}
            {!loading && items.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-gray-400">{tr('empty')}</td></tr>
            )}
            {!loading && items.map((row) => {
              const open = expanded === row.id;
              const rows = diffRows(row.old_values, row.new_values);
              return [
                <tr key={row.id} className="border-t border-gray-100 hover:bg-gray-50 cursor-pointer"
                  onClick={() => setExpanded(open ? null : row.id)}>
                  <td className="px-3 py-2 text-gray-400">{open ? '▾' : '▸'}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{fmtDt(row.created_at)}</td>
                  <td className="px-3 py-2">{row.user_name || (row.user_id ? `#${row.user_id}` : '—')}</td>
                  <td className="px-3 py-2"><span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 text-xs font-mono">{row.action}</span></td>
                  <td className="px-3 py-2 whitespace-nowrap">{row.entity_type}{row.entity_id != null ? ` #${row.entity_id}` : ''}</td>
                  <td className="px-3 py-2">{row.branch_name || (row.branch_id ? `#${row.branch_id}` : '—')}</td>
                  <td className="px-3 py-2 text-gray-500 font-mono text-xs">{row.ip_address || '—'}</td>
                </tr>,
                open && (
                  <tr key={`${row.id}-d`} className="bg-gray-50 border-t border-gray-100">
                    <td colSpan={7} className="px-4 py-3">
                      {rows.length === 0 ? (
                        <div className="text-gray-400 text-xs">{tr('no_changes')}</div>
                      ) : (
                        <table className="text-xs w-full">
                          <thead className="text-gray-500">
                            <tr>
                              <th className="text-left px-2 py-1 w-1/4">{tr('field')}</th>
                              <th className="text-left px-2 py-1">{tr('old')}</th>
                              <th className="text-left px-2 py-1">{tr('new')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {rows.map((r) => (
                              <tr key={r.key} className={r.changed ? 'bg-yellow-50' : ''}>
                                <td className="px-2 py-1 font-mono text-gray-700">{r.key}</td>
                                <td className={`px-2 py-1 break-all ${r.changed ? 'text-red-700 line-through' : 'text-gray-500'}`}>{fmtVal(r.oldVal)}</td>
                                <td className={`px-2 py-1 break-all ${r.changed ? 'text-green-700 font-medium' : 'text-gray-500'}`}>{fmtVal(r.newVal)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </td>
                  </tr>
                ),
              ];
            })}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm">
        <button disabled={page === 0} onClick={() => { setPage((p) => p - 1); setExpanded(null); }}
          className="px-3 py-1.5 rounded-lg bg-gray-100 disabled:opacity-40">{tr('prev')}</button>
        <span className="text-gray-500">{tr('page')} {page + 1} / {pages}</span>
        <button disabled={page + 1 >= pages} onClick={() => { setPage((p) => p + 1); setExpanded(null); }}
          className="px-3 py-1.5 rounded-lg bg-gray-100 disabled:opacity-40">{tr('next')}</button>
      </div>
    </div>
  );
}
