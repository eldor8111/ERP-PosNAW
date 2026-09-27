import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Truck, Wallet, TrendingUp, AlertTriangle } from 'lucide-react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import { StatCard } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/ui/DataTable';

const fmt = (n) => Number(n ?? 0).toLocaleString('uz-UZ', { maximumFractionDigits: 0 });
const PERIODS = [7, 30, 90];

// Limitdan foydalanish darajasi: 80% dan yuqori — ogohlantirish, oshgan — xavf
function LimitUsage({ row, t }) {
  if (row.limit_usage == null) return <span className="text-ink-300">{t('distributor.noLimit')}</span>;
  const pct = row.limit_usage;
  const color = row.over_limit ? 'danger' : pct >= 80 ? 'warning' : 'success';
  const barCls = { danger: 'bg-danger', warning: 'bg-warning', success: 'bg-success' }[color];
  return (
    <div className="flex items-center gap-2 justify-end">
      <div className="w-20 h-1.5 rounded-full bg-surface-sunken overflow-hidden">
        <div className={`h-full ${barCls}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <Badge color={color} dot={false}>{pct}%</Badge>
    </div>
  );
}

/** Distribyutorlar reytingi: davr bo'yicha xarid, qarz va kredit limiti */
export default function DistributorsReport({ refreshKey }) {
  const { t } = useLang();
  const navigate = useNavigate();
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get('/customers/distributors-report', { params: { days }, _silent: true })
      .then(r => setData(r.data))
      .catch(() => setData({ items: [], totals: {} }));
  }, [days, refreshKey]);

  const totals = data?.totals || {};
  const columns = [
    { key: 'rank', label: '№', render: r => data.items.indexOf(r) + 1 },
    {
      key: 'name', label: t('common.name'), render: r => (
        <div>
          <div className="font-medium text-brand">{r.name}</div>
          <div className="text-xs text-ink-300">{r.phone || '—'}</div>
        </div>
      ),
    },
    { key: 'territory', label: t('distributor.territory'), render: r => r.territory || <span className="text-ink-300">—</span> },
    { key: 'sales', label: t('distributor.periodSales'), align: 'right', numeric: true, render: r => `${fmt(r.sales)}` },
    { key: 'sale_count', label: t('distributor.saleCount'), align: 'right', numeric: true },
    {
      key: 'debt', label: t('customer.debtBalance'), align: 'right', numeric: true,
      render: r => <span className={r.debt > 0 ? 'text-danger font-semibold' : ''}>{fmt(r.debt)}</span>,
    },
    { key: 'debt_limit', label: t('customer.creditLimit'), align: 'right', numeric: true, render: r => r.debt_limit > 0 ? fmt(r.debt_limit) : '—' },
    { key: 'limit_usage', label: t('distributor.limitUsage'), align: 'right', render: r => <LimitUsage row={r} t={t} /> },
    {
      key: 'last_sale_at', label: t('distributor.lastPurchase'),
      render: r => r.last_sale_at ? new Date(r.last_sale_at).toLocaleDateString('uz-UZ') : <span className="text-ink-300">—</span>,
    },
  ];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard icon={<Truck className="size-5" />} label={t('distributor.count')} value={totals.count ?? 0} />
        <StatCard icon={<TrendingUp className="size-5" />} color="success" label={`${t('distributor.periodSales')} (${days} ${t('distributor.days')})`} value={fmt(totals.sales)} />
        <StatCard icon={<Wallet className="size-5" />} color="warning" label={t('distributor.totalDebt')} value={fmt(totals.debt)} />
        <StatCard icon={<AlertTriangle className="size-5" />} color="danger" label={t('distributor.overLimit')} value={totals.over_limit ?? 0} />
      </div>

      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink-900">{t('distributor.ranking')}</h3>
        <div className="flex gap-0.5 bg-surface-sunken p-0.5 rounded-lg">
          {PERIODS.map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${days === d ? 'bg-surface text-ink-900 shadow-sm' : 'text-ink-500 hover:text-ink-900'}`}>
              {d} {t('distributor.days')}
            </button>
          ))}
        </div>
      </div>

      <DataTable
        columns={columns}
        rows={data?.items || []}
        emptyText={data ? t('distributor.empty') : '...'}
        onRowClick={r => navigate(`/admin/customers/${r.id}`)}
      />
    </div>
  );
}
