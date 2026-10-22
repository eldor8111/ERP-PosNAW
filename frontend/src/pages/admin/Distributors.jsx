import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Truck, Wallet, TrendingUp, AlertTriangle, Map, List, Search, Download, ExternalLink, MapPin } from 'lucide-react';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import { StatCard } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/ui/DataTable';
import MultiMap from '../../components/MultiMap';

const fmt = (n) => Number(n ?? 0).toLocaleString('uz-UZ', { maximumFractionDigits: 0 });
const PERIODS = [7, 30, 90];

// Limitdan foydalanish darajasi: 80% dan yuqori — ogohlantirish, oshgan — xavf
function LimitUsage({ row, t }) {
  if (row.limit_usage == null) return <span className="text-ink-300">{t('distributor.noLimit') || 'Cheksiz'}</span>;
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

/** Distribyutorlar reytingi va geografik xaritasi: davr bo'yicha xarid, qarz va kredit limiti */
export default function DistributorsReport({ refreshKey }) {
  const { t } = useLang();
  const navigate = useNavigate();
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [viewMode, setViewMode] = useState('table'); // 'table' | 'map'
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all'); // 'all' | 'over_limit' | 'warning' | 'debt'
  const [territoryFilter, setTerritoryFilter] = useState('all');
  const [activeMarkerId, setActiveMarkerId] = useState(null);

  useEffect(() => {
    api.get('/customers/distributors-report', { params: { days }, _silent: true })
      .then(r => setData(r.data))
      .catch(() => setData({ items: [], totals: {} }));
  }, [days, refreshKey]);

  const rawItems = data?.items || [];
  const totals = data?.totals || {};

  // Mavjud hududlar ro'yxati
  const territories = useMemo(() => {
    const set = new Set();
    rawItems.forEach(i => {
      if (i.territory) set.add(i.territory);
    });
    return Array.from(set).sort();
  }, [rawItems]);

  // Hisoblangan filterlar
  const counts = useMemo(() => {
    return {
      total: rawItems.length,
      overLimit: rawItems.filter(i => i.over_limit).length,
      warning: rawItems.filter(i => !i.over_limit && i.limit_usage >= 80).length,
      debt: rawItems.filter(i => i.debt > 0).length,
    };
  }, [rawItems]);

  // Qidiruv va filtrlar qo'llash
  const filteredItems = useMemo(() => {
    return rawItems.filter(item => {
      // Qidiruv
      if (search.trim()) {
        const q = search.toLowerCase();
        const matches = (
          (item.name && item.name.toLowerCase().includes(q)) ||
          (item.phone && item.phone.toLowerCase().includes(q)) ||
          (item.territory && item.territory.toLowerCase().includes(q)) ||
          (item.region && item.region.toLowerCase().includes(q)) ||
          (item.address && item.address.toLowerCase().includes(q))
        );
        if (!matches) return false;
      }

      // Status
      if (statusFilter === 'over_limit' && !item.over_limit) return false;
      if (statusFilter === 'warning' && (item.over_limit || (item.limit_usage ?? 0) < 80)) return false;
      if (statusFilter === 'debt' && !(item.debt > 0)) return false;

      // Hudud
      if (territoryFilter !== 'all' && item.territory !== territoryFilter) return false;

      return true;
    });
  }, [rawItems, search, statusFilter, territoryFilter]);

  // Xarita markerlari
  const mapMarkers = useMemo(() => {
    return filteredItems
      .filter(item => item.lat != null && item.lng != null)
      .map((item, idx) => {
        const isOver = item.over_limit;
        const isWarn = !isOver && item.limit_usage >= 80;
        const color = isOver ? '#EF4444' : isWarn ? '#F59E0B' : item.debt > 0 ? '#10B981' : '#64748B';

        const popupHtml = `
          <div style="font-family:Inter,system-ui,sans-serif;min-width:210px;padding:3px;">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
              <span style="font-size:11px;font-weight:800;color:${color};background:${color}18;padding:2px 6px;border-radius:6px;">№${idx + 1} Distribyutor</span>
              ${item.territory ? `<span style="font-size:11px;color:#64748B;font-weight:600;">🏙 ${item.territory}</span>` : ''}
            </div>
            <div style="font-size:14px;font-weight:700;color:#0F172A;line-height:1.3;margin-bottom:2px;">${item.name}</div>
            ${item.phone ? `<div style="font-size:11px;color:#64748B;">📞 ${item.phone}</div>` : ''}
            ${item.address ? `<div style="font-size:11px;color:#64748B;margin-top:2px;">📍 ${item.address}</div>` : ''}
            <div style="margin-top:6px;padding-top:6px;border-top:1px solid #E2E8F0;display:flex;flex-direction:column;gap:3px;">
              <div style="font-size:11px;color:#334155;">💰 Davr xaridi: <b>${fmt(item.sales)} so'm</b> (${item.sale_count} ta)</div>
              <div style="font-size:11px;color:${item.debt > 0 ? '#DC2626' : '#334155'};">
                Qarz: <b>${fmt(item.debt)} so'm</b> ${item.debt_limit > 0 ? `/ Limit: ${fmt(item.debt_limit)} so'm` : ''}
              </div>
              ${item.limit_usage != null ? `<div style="font-size:10px;font-weight:700;color:${color};">Limit bandligi: ${item.limit_usage}% ${isOver ? '(⚠️ Limitdan oshgan!)' : ''}</div>` : ''}
            </div>
          </div>
        `;

        return {
          id: item.id,
          lat: item.lat,
          lng: item.lng,
          label: item.name,
          subLabel: item.debt > 0 ? `Qarz: ${fmt(item.debt)}` : `Savdo: ${fmt(item.sales)}`,
          badge: idx + 1,
          color,
          isWarning: isOver,
          htmlPopup: popupHtml,
          title: `${item.name} · ${item.territory || ''}`,
        };
      });
  }, [filteredItems]);

  // CSV eksport
  const exportCsv = () => {
    if (!filteredItems.length) return;
    const headers = ['№', 'Nomi', 'Telefon', 'Hudud', 'Viloyat', 'Davr xaridi', 'Sotuvlar soni', 'Qarz balansi', 'Kredit limiti', 'Limit bandligi %', 'Oxirgi xarid'];
    const rows = filteredItems.map((r, i) => [
      i + 1,
      `"${(r.name || '').replace(/"/g, '""')}"`,
      `"${r.phone || ''}"`,
      `"${(r.territory || '').replace(/"/g, '""')}"`,
      `"${(r.region || '').replace(/"/g, '""')}"`,
      r.sales ?? 0,
      r.sale_count ?? 0,
      r.debt ?? 0,
      r.debt_limit ?? 0,
      r.limit_usage ?? '',
      r.last_sale_at ? new Date(r.last_sale_at).toLocaleDateString('uz-UZ') : '',
    ]);

    const csvContent = '\uFEFF' + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `distribyutorlar_${days}kun_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const columns = [
    { key: 'rank', label: '№', render: r => filteredItems.indexOf(r) + 1 },
    {
      key: 'name', label: t('common.name'), render: r => (
        <div>
          <div className="font-semibold text-brand flex items-center gap-1.5">
            {r.name}
            {r.lat != null && <MapPin className="size-3.5 text-slate-400" title="GPS nuqtasi bor" />}
          </div>
          <div className="text-xs text-ink-400">{r.phone || '—'}{r.address ? ` · ${r.address}` : ''}</div>
        </div>
      ),
    },
    { key: 'territory', label: t('distributor.territory'), render: r => r.territory ? `${r.territory}${r.region ? ` (${r.region})` : ''}` : <span className="text-ink-300">—</span> },
    { key: 'sales', label: t('distributor.periodSales'), align: 'right', numeric: true, render: r => `${fmt(r.sales)}` },
    { key: 'sale_count', label: t('distributor.saleCount'), align: 'right', numeric: true },
    {
      key: 'debt', label: t('customer.debtBalance'), align: 'right', numeric: true,
      render: r => <span className={r.debt > 0 ? 'text-danger font-bold' : ''}>{fmt(r.debt)}</span>,
    },
    { key: 'debt_limit', label: t('customer.creditLimit'), align: 'right', numeric: true, render: r => r.debt_limit > 0 ? fmt(r.debt_limit) : '—' },
    { key: 'limit_usage', label: t('distributor.limitUsage'), align: 'right', render: r => <LimitUsage row={r} t={t} /> },
    {
      key: 'last_sale_at', label: t('distributor.lastPurchase'),
      render: r => r.last_sale_at ? new Date(r.last_sale_at).toLocaleDateString('uz-UZ') : <span className="text-ink-300">—</span>,
    },
  ];

  return (
    <div className="space-y-4">
      {/* KPI Kartochkalari */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard icon={<Truck className="size-5" />} label={t('distributor.count')} value={totals.count ?? 0} />
        <StatCard icon={<TrendingUp className="size-5" />} color="success" label={`${t('distributor.periodSales')} (${days} ${t('distributor.days')})`} value={fmt(totals.sales)} />
        <StatCard icon={<Wallet className="size-5" />} color="warning" label={t('distributor.totalDebt')} value={fmt(totals.debt)} />
        <StatCard icon={<AlertTriangle className="size-5" />} color="danger" label={t('distributor.overLimit')} value={totals.over_limit ?? 0} />
      </div>

      {/* Boshqaruv paneli: Davr, Qidiruv, Hudud, Ko'rinish rejimi */}
      <div className="bg-surface border border-line rounded-2xl p-3.5 space-y-3 shadow-sm">
        <div className="flex items-center justify-between flex-wrap gap-3">
          {/* Chap: Qidiruv va Hudud */}
          <div className="flex items-center gap-2 flex-1 min-w-[280px]">
            <div className="relative flex-1">
              <Search className="size-4 text-ink-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Distribyutor, telefon yoki hudud qidirish..."
                className="w-full pl-9 pr-3 py-1.5 text-sm bg-surface-sunken border border-line rounded-xl focus:outline-none focus:border-brand"
              />
            </div>
            {territories.length > 0 && (
              <select
                value={territoryFilter}
                onChange={e => setTerritoryFilter(e.target.value)}
                className="px-3 py-1.5 text-sm bg-surface-sunken border border-line rounded-xl text-ink-700"
              >
                <option value="all">Barcha hududlar</option>
                {territories.map(tr => (
                  <option key={tr} value={tr}>{tr}</option>
                ))}
              </select>
            )}
          </div>

          {/* O'ng: Davr tanlash, Ko'rinish rejimi, Eksport */}
          <div className="flex items-center gap-2">
            {/* Davr */}
            <div className="flex gap-0.5 bg-surface-sunken p-0.5 rounded-lg">
              {PERIODS.map(d => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${days === d ? 'bg-surface text-ink-900 shadow-sm' : 'text-ink-500 hover:text-ink-900'}`}
                >
                  {d} {t('distributor.days')}
                </button>
              ))}
            </div>

            {/* Jadval / Xarita tugmasi */}
            <div className="flex gap-0.5 bg-surface-sunken p-0.5 rounded-lg border border-line">
              <button
                onClick={() => setViewMode('table')}
                className={`flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${viewMode === 'table' ? 'bg-brand text-white shadow-sm' : 'text-ink-600 hover:text-ink-900'}`}
                title="Jadval ko'rinishi"
              >
                <List className="size-3.5" />
                <span>Jadval</span>
              </button>
              <button
                onClick={() => setViewMode('map')}
                className={`flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${viewMode === 'map' ? 'bg-brand text-white shadow-sm' : 'text-ink-600 hover:text-ink-900'}`}
                title="Geografik xarita"
              >
                <Map className="size-3.5" />
                <span>Xarita</span>
              </button>
            </div>

            {/* CSV yuklab olish */}
            <button
              onClick={exportCsv}
              className="p-1.5 text-ink-600 hover:text-brand bg-surface-sunken hover:bg-brand/10 border border-line rounded-lg"
              title="CSV / Excel yuklab olish"
            >
              <Download className="size-4" />
            </button>
          </div>
        </div>

        {/* Holat filtri chiplari */}
        <div className="flex items-center gap-2 flex-wrap pt-1 border-t border-line/50 text-xs">
          <span className="text-ink-400 font-medium">Holat:</span>
          <button
            onClick={() => setStatusFilter('all')}
            className={`px-2.5 py-1 rounded-lg font-semibold transition-all ${statusFilter === 'all' ? 'bg-ink-900 text-white' : 'bg-surface-sunken text-ink-600 hover:bg-slate-200'}`}
          >
            Barchasi ({counts.total})
          </button>
          <button
            onClick={() => setStatusFilter('over_limit')}
            className={`px-2.5 py-1 rounded-lg font-semibold transition-all ${statusFilter === 'over_limit' ? 'bg-danger text-white' : 'bg-danger/10 text-danger hover:bg-danger/20'}`}
          >
            ⚠️ Limitdan oshgan ({counts.overLimit})
          </button>
          <button
            onClick={() => setStatusFilter('warning')}
            className={`px-2.5 py-1 rounded-lg font-semibold transition-all ${statusFilter === 'warning' ? 'bg-warning text-white' : 'bg-warning/10 text-warning hover:bg-warning/20'}`}
          >
            ⚡ Xavfli 80-100% ({counts.warning})
          </button>
          <button
            onClick={() => setStatusFilter('debt')}
            className={`px-2.5 py-1 rounded-lg font-semibold transition-all ${statusFilter === 'debt' ? 'bg-brand text-white' : 'bg-brand/10 text-brand hover:bg-brand/20'}`}
          >
            💰 Qarzli distribyutorlar ({counts.debt})
          </button>
        </div>
      </div>

      {/* Ko'rinish: Jadval yoki Xarita */}
      {viewMode === 'map' ? (
        <div className="space-y-2">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 space-y-2">
              <MultiMap
                markers={mapMarkers}
                height={560}
                activeMarkerId={activeMarkerId}
                onMarkerClick={(id) => setActiveMarkerId(id)}
                fitKey={`dist-map-${mapMarkers.length}-${statusFilter}`}
              />
              <div className="flex items-center justify-between flex-wrap gap-2 px-3 py-2 bg-surface border border-line rounded-xl text-xs text-ink-700">
                <span className="font-semibold text-ink-900">Marker ranglari:</span>
                <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-emerald-500 shrink-0" /><span>Me'yorda</span></div>
                <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-amber-500 shrink-0" /><span>Xavfli (80-100%)</span></div>
                <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-red-500 shrink-0" /><span className="text-danger font-semibold">Limitdan oshgan</span></div>
                <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-slate-500 shrink-0" /><span>Qarzsiz / Limitsiz</span></div>
              </div>
            </div>

            {/* Xaritadagi distribyutorlar yon paneli */}
            <div className="space-y-2 max-h-[610px] overflow-y-auto pr-1">
              <div className="text-xs font-bold text-ink-500 uppercase tracking-wider px-1">
                Xaritadagi distribyutorlar ({mapMarkers.length} / {filteredItems.length})
              </div>
              {filteredItems.map((r, idx) => {
                const isSelected = activeMarkerId === r.id;
                const isOver = r.over_limit;
                const isWarn = !isOver && r.limit_usage >= 80;

                return (
                  <div
                    key={r.id}
                    onClick={() => {
                      if (r.lat != null) setActiveMarkerId(r.id);
                    }}
                    className={`bg-surface border rounded-xl p-3 text-sm transition-all cursor-pointer ${
                      isSelected
                        ? 'ring-2 ring-brand border-brand shadow-sm'
                        : isOver
                        ? 'border-danger/40 bg-red-50/20'
                        : isWarn
                        ? 'border-warning/40'
                        : 'border-line hover:border-brand/40'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="font-bold text-ink-900 flex items-center gap-1.5 truncate">
                          <span>#{idx + 1} {r.name}</span>
                          {r.lat == null && <span className="text-[10px] text-ink-400 bg-surface-sunken px-1.5 py-0.5 rounded">GPS yo'q</span>}
                        </div>
                        {r.territory && <div className="text-xs text-ink-500 mt-0.5">🏙 {r.territory}</div>}
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/admin/customers/${r.id}`);
                        }}
                        className="p-1 text-ink-400 hover:text-brand"
                        title="Profilga o'tish"
                      >
                        <ExternalLink className="size-4" />
                      </button>
                    </div>

                    <div className="flex items-center justify-between text-xs mt-2 pt-2 border-t border-line/60">
                      <div>
                        <span className="text-ink-400">Xarid: </span>
                        <span className="font-semibold text-ink-900">{fmt(r.sales)}</span>
                      </div>
                      <div>
                        <span className="text-ink-400">Qarz: </span>
                        <span className={`font-bold ${r.debt > 0 ? 'text-danger' : 'text-ink-900'}`}>{fmt(r.debt)}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        <DataTable
          columns={columns}
          rows={filteredItems}
          emptyText={data ? t('distributor.empty') : '...'}
          onRowClick={r => navigate(`/admin/customers/${r.id}`)}
        />
      )}
    </div>
  );
}
