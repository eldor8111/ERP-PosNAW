import { useState, useEffect } from 'react';
import {
    AreaChart, Area, BarChart, Bar,
    XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, Line, ComposedChart, ReferenceLine,
} from 'recharts';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import api from '../../api/axios';
import { useLang } from '../../context/LangContext';
import toast from 'react-hot-toast';
import { Listbox, ListboxButton, ListboxOptions, ListboxOption } from '@headlessui/react';
import { ChevronsUpDown, CheckIcon, Building2, Warehouse } from 'lucide-react'; // Ikonkalar uchun (ixtiyoriy)

const fmt = (val) => {
    if (!val) return "0 so'm";
    const n = Number(val);
    if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + " mlrd";
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + " mln";
    if (n >= 1_000) return (n / 1_000).toFixed(0) + " K";
    return n.toLocaleString('uz-UZ') + " so'm";
};

const fmtFull = (val) => {
    if (!val) return "0 so'm";
    return Number(val).toLocaleString('uz-UZ') + " so'm";
};

function KpiCard({ label, value, sub, icon, gradient, iconBg, badge }) {
    return (
        <div className={`relative overflow-hidden rounded-2xl p-6 text-white ${gradient}`}>
            <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white/70">{label}</p>
                    <p className="mt-2 text-2xl font-bold truncate">{value}</p>
                    {sub && <p className="mt-1 text-sm text-white/60">{sub}</p>}
                </div>
                <div className="flex flex-col items-end gap-2 ml-3">
                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${iconBg}`}>
                        {icon}
                    </div>
                    {badge != null && (
                        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${badge > 0 ? 'bg-white/20 text-white' : badge < 0 ? 'bg-red-500/30 text-white' : 'bg-white/10 text-white/60'
                            }`}>
                            {badge > 0 ? `+${badge}%` : badge < 0 ? `${badge}%` : '—'}
                        </span>
                    )}
                </div>
            </div>
            <div className="absolute -bottom-4 -right-4 w-24 h-24 rounded-full bg-white/10" />
        </div>
    );
}

const CustomTooltip = ({ active, payload, label }) => {
    const { t } = useLang();
    if (!active || !payload?.length) return null;
    return (
        <div className="bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 shadow-xl">
            <p className="text-slate-400 text-xs mb-1">{label}</p>
            <p className="text-white text-sm font-semibold">{fmtFull(payload[0]?.value)}</p>
            {payload[1] && <p className="text-slate-300 text-xs mt-0.5">{payload[1]?.value} {t('dashboard.salesCount')}</p>}
        </div>
    );
};

export default function Profile() {
    const { user } = useAuth();
    const { t } = useLang();
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [warehouses, setWarehouses] = useState([]);
    const [branches, setBranches] = useState([]);
    const [warehouseId, setWarehouseId] = useState(() => {
        const saved = localStorage.getItem('dashboard_warehouse_id');
        return saved ? Number(saved) : '';
    });
    const [branchId, setBranchId] = useState(() => {
        const saved = localStorage.getItem('dashboard_branch_id');
        return saved ? Number(saved) : '';
    });

    useEffect(() => {
        if (user?.role !== 'super_admin') {

            api.get('/warehouses').then(r => setWarehouses(r.data)).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
            api.get('/branches').then(r => setBranches(r.data.filter(b => b.is_active))).catch((err) => { toast.error(err.response?.data?.detail || err.message || "Xatolik yuz berdi") });
        }
    }, [user]);

    const UserCreatedAt = user.created_at;
    const dateObj = new Date(UserCreatedAt);

    const load = (showSpinner = false) => {
        if (user?.role === 'super_admin') return;
        if (showSpinner) setLoading(true);
        setError(null);
        const params = {};
        if (warehouseId) params.warehouse_id = warehouseId;
        if (branchId) params.branch_id = branchId;
        api.get('/reports/dashboard', { params })
            .then(res => { setData(res.data); setError(null); })
            .catch(err => {
                const msg = err?.response?.data?.detail || err?.message || "Noma'lum xato";
                setError(msg);
            })
            .finally(() => setLoading(false));
    };

    useEffect(() => {
        load(true);
        const interval = setInterval(() => load(false), 120_000);
        return () => clearInterval(interval);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [warehouseId, branchId]);

    const handleWarehouseChange = (e) => {
        const val = e.target.value;
        setWarehouseId(val ? Number(val) : '');
        if (val) localStorage.setItem('dashboard_warehouse_id', val);
        else localStorage.removeItem('dashboard_warehouse_id');
    };

    const handleBranchChange = (e) => {
        const val = e.target.value;
        setBranchId(val ? Number(val) : '');
        if (val) localStorage.setItem('dashboard_branch_id', val);
        else localStorage.removeItem('dashboard_branch_id');
    };

    // super_admin uchun — dashboard ko'rsatilmaydi, to'g'ridan-to'g'ri redirect
    if (user?.role === 'super_admin') {
        return <Navigate to="/admin/super-admin" replace />;
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="flex flex-col items-center gap-4">
                    <div className="relative">
                        <div className="w-14 h-14 border-4 border-indigo-100 rounded-full" />
                        <div className="absolute inset-0 w-14 h-14 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                    </div>
                    <p className="text-slate-500 text-sm font-medium">{t('common.loading')}</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="text-center bg-white rounded-2xl p-8 shadow-sm border border-slate-100 max-w-sm">
                    <div className="w-14 h-14 bg-rose-50 rounded-full flex items-center justify-center mx-auto mb-4">
                        <svg className="w-7 h-7 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                    </div>
                    <p className="text-slate-700 font-semibold text-lg">{t('dashboard.errorTitle')}</p>
                    <p className="text-slate-400 text-sm mt-1 mb-5">{t('dashboard.errorDesc')}</p>
                    <button onClick={load} className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-xl transition-colors shadow-lg shadow-indigo-200">
                        {t('common.refresh')}
                    </button>
                </div>
            </div>
        );
    }

    if (!data) return null;
    const kpis = [
        {
            label: t('dashboard.todaySales'),
            value: fmt(data.today?.sales),
            sub: `${data.today?.orders ?? 0} ${t('common.item')} ${t('sale.title').toLowerCase()}`,
            badge: data.today?.change_pct,
            gradient: "bg-linear-to-br from-indigo-500 to-indigo-700",
            iconBg: "bg-white/20",
            icon: (
                <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
            ),
        },
        {
            label: t('dashboard.totalSales'),
            value: fmt(data.monthly?.sales),
            sub: `${data.monthly?.orders ?? 0} ${t('common.item')} ${t('sale.title').toLowerCase()}`,
            gradient: "bg-linear-to-br from-emerald-500 to-emerald-700",
            iconBg: "bg-white/20",
            icon: (
                <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                </svg>
            ),
        },
        {
            label: t('dashboard.profit'),
            value: fmt(data.monthly?.profit),
            sub: t('common.summary'),
            gradient: "bg-linear-to-br from-violet-500 to-violet-700",
            iconBg: "bg-white/20",
            icon: (
                <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                </svg>
            ),
        },
        {
            label: t('dashboard.lowStock'),
            value: `${data.inventory?.low_stock_count ?? 0} ${t('common.item')}`,
            sub: `${t('product.outOfStock')}: ${data.inventory?.dead_stock_count ?? 0} ${t('common.item')}`,
            gradient: "bg-linear-to-br from-rose-500 to-rose-700",
            iconBg: "bg-white/20",
            icon: (
                <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
            ),
        },
        {
            label: t('customer.totalDebt'),
            value: fmt(data.debts?.total_debt),
            sub: data.debts?.overdue_count > 0
                ? `⚠ ${data.debts.overdue_count} ${t('common.item')} ${t('common.warning').toLowerCase()}`
                : `${data.debts?.debtor_count ?? 0} ${t('common.item')} ${t('customer.totalDebtors').toLowerCase()}`,
            gradient: data.debts?.overdue_count > 0
                ? "bg-linear-to-br from-orange-500 to-red-600"
                : "bg-linear-to-br from-amber-500 to-amber-700",
            iconBg: "bg-white/20",
            icon: (
                <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" />
                </svg>
            ),
        },
    ];

    return (
        <div className="space-y-5">
            <div className="relative w-full overflow-hidden bg-white border border-gray-100 rounded-2xl shadow-sm transition-all duration-300 group">

                {/* Background Dizayn Elementlari: To'rsimon fon va nozik yorug'lik effekti */}
                <div className="absolute inset-0 opacity-[0.4] pointer-events-none mix-blend-multiply bg-[linear-gradient(to_right,#f0f0f0_1px,transparent_1px),linear-gradient(to_bottom,#f0f0f0_1px,transparent_1px)] bg-[size:2rem_2rem]"></div>
                <div className="absolute -top-24 -right-24 w-80 h-80 bg-indigo-400/10 rounded-full blur-3xl group-hover:bg-indigo-400/15 transition-all duration-500 pointer-events-none"></div>
                <div className="absolute -bottom-24 -left-24 w-80 h-80 bg-violet-400/10 rounded-full blur-3xl pointer-events-none"></div>

                {/* Asosiy Kontent - Max-w cheklovisiz, chekkalarga chiroyli padding bilan */}
                <div className="relative z-10 p-6 sm:p-8 flex flex-col md:flex-row items-center justify-between gap-6">

                    {/* Chap tomon: Avatar va Ma'lumotlar bloki */}
                    <div className="flex flex-col sm:flex-row items-center gap-6 text-center sm:text-left w-full md:w-auto">

                        {/* Zamonaviy Avatar halqasi */}
                        <div className="relative flex-shrink-0">
                            <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-full bg-gradient-to-tr from-indigo-500 via-purple-500 to-pink-500 p-[3px] shadow-md shadow-indigo-100">
                                <div className="w-full h-full rounded-full bg-indigo-50 flex items-center justify-center border-2 border-white">
                                    <span className="text-indigo-600 text-2xl sm:text-4xl font-black tracking-wide">
                                        {user.name?.charAt(0).toUpperCase() || 'U'}
                                    </span>
                                </div>
                            </div>
                            {/* Pulsatsiyalanuvchi online indicator */}
                            <span className="absolute bottom-1 right-1 block h-4 w-4 rounded-full ring-4 ring-white bg-emerald-500 shadow-sm"></span>
                        </div>

                        {/* Matnli Kontent */}
                        <div className="space-y-2">
                            <div className="flex flex-col sm:flex-row items-center gap-3">
                                <h2 className="text-2xl sm:text-3xl font-extrabold text-gray-900 tracking-tight">
                                    {user.name ? user.name.charAt(0).toUpperCase() + user.name.slice(1) : "Noma'lum foydalanuvchi"}
                                </h2>
                                <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-gradient-to-r from-indigo-50 to-purple-50 text-indigo-700 border border-indigo-100/60 shadow-sm uppercase tracking-wider">
                                    {user.role || "Foydalanuvchi"}
                                </span>
                            </div>

                            {/* Ikonkali va tartibli aloqa/sana qismi */}
                            <div className="flex flex-wrap items-center justify-center sm:justify-start gap-x-5 gap-y-2 text-sm text-gray-500 font-medium">
                                <div className="flex items-center gap-2 text-gray-700 bg-gray-50/80 px-2.5 py-1 rounded-lg border border-gray-100/50 backdrop-blur-sm">
                                    <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.387a12.035 12.035 0 01-7.108-7.108c-.155-.44.01-1.29.387-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z" />
                                    </svg>
                                    <span>+{user.phone || "Mavjud emas"}</span>
                                </div>

                                <div className="flex items-center gap-2 bg-gray-50/80 px-2.5 py-1 text-gray-500">
                                    <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5m-9-6h.008v.008H12v-.008zM12 15h.008v.008H12V15zm0 2.25h.008v.008H12v-.008zM9.75 15h.008v.008H9.75V15zm0 2.25h.008v.008H9.75v-.008zM7.5 15h.008v.008H7.5V15zm0 2.25h.008v.008H7.5v-.008zM14.25 15h.008v.008H14.25V15zm0 2.25h.008v.008H14.25v-.008zM16.5 15h.008v.008H16.5V15zm0 2.25h.008v.008H16.5v-.008z" />
                                    </svg>
                                    <span>{dateObj.toLocaleDateString('uz-UZ')} da tizimga qo'shilgan</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* O'ng tomon: Neon effektli Tahrirlash tugmasi */}
                    <button className="w-full md:w-auto inline-flex items-center justify-center gap-2.5 px-6 py-3 text-sm font-bold text-white bg-gradient-to-r from-indigo-600 to-violet-600 rounded-xl shadow-sm hover:from-indigo-500 hover:to-violet-500 active:scale-[0.98] transition-all duration-200 cursor-pointer border border-indigo-500/10 focus:outline-none focus:ring-2 focus:ring-indigo-500/20">
                        <svg className="w-4 h-4 text-indigo-100" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L6.832 19.82a4.5 4.5 0 01-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 011.13-1.897L16.863 4.487zm0 0L19.5 7.125" />
                        </svg>
                        Tahrirlash
                    </button>

                </div>
            </div>

            {/* Toolbar */}
            <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-4 flex-wrap w-full sm:w-auto">
                    {/* 1. FILIALLAR (BRANCHES) SELECTBOX */}
                    {branches.length > 0 && (
                        <div className="flex flex-col w-max">
                            <Listbox
                                value={branchId}
                                onChange={(value) => handleBranchChange({ target: { value } })} // Eski handleBranchChange mantiqini buzmaslik uchun
                            >
                                <div className="relative">
                                    <ListboxButton className="w-full cursor-pointer flex items-center px-3 py-2 justify-between rounded-lg border border-slate-200 text-[1rem] bg-white text-slate-900 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors shadow-sm text-left">
                                        <span className="flex items-center gap-3">
                                            <Building2 className="size-5 shrink-0 text-slate-400" />
                                            <span className="block truncate">
                                                {branches.find(b => b.id === branchId)?.name || t('common.allBranches')}
                                            </span>
                                        </span>
                                        <ChevronsUpDown
                                            aria-hidden="true"
                                            className="size-5 ml-2 text-gray-400"
                                        />
                                    </ListboxButton>

                                    <ListboxOptions
                                        transition
                                        className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md outline-0 bg-white text-base border border-slate-200 transition duration-100 ease-in data-[closed]:opacity-0 sm:text-sm shadow-lg"
                                    >
                                        {/* Barcha filiallar varianti (Bo'sh qiymat uchun) */}
                                        <ListboxOption
                                            value=""
                                            className="group relative py-2.5 pr-9 pl-3 select-none cursor-pointer text-slate-800 data-[focus]:bg-indigo-600 data-[focus]:text-white outline-hidden"
                                        >
                                            <div className="flex items-center gap-3">
                                                <Building2 className="size-5 shrink-0 text-gray-400 group-data-[focus]:text-white" />
                                                <span className="block truncate font-normal group-data-[selected]:font-semibold">
                                                    {t('common.allBranches')}
                                                </span>
                                            </div>
                                            <span className="absolute inset-y-0 right-0 flex items-center pr-4 text-indigo-600 group-not-data-[selected]:hidden group-data-[focus]:text-white">
                                                <CheckIcon aria-hidden="true" className="size-5" />
                                            </span>
                                        </ListboxOption>

                                        {/* Dinamik filiallar ro'yxati */}
                                        {branches.map((b) => (
                                            <ListboxOption
                                                key={b.id}
                                                value={b.id}
                                                className="group relative py-2.5 pr-9 pl-3 select-none cursor-pointer text-slate-800 data-[focus]:bg-indigo-600 data-[focus]:text-white outline-hidden"
                                            >
                                                <div className="flex items-center gap-3">
                                                    <Building2 className="size-5 shrink-0 text-gray-400 group-data-[focus]:text-white" />
                                                    <span className="block truncate font-normal group-data-[selected]:font-semibold">
                                                        {b.name}
                                                    </span>
                                                </div>

                                                <span className="absolute inset-y-0 right-0 flex items-center pr-4 text-indigo-600 group-not-data-[selected]:hidden group-data-[focus]:text-white">
                                                    <CheckIcon aria-hidden="true" className="size-5" />
                                                </span>
                                            </ListboxOption>
                                        ))}
                                    </ListboxOptions>
                                </div>
                            </Listbox>
                        </div>
                    )}

                    {/* 2. OMBORLAR (WAREHOUSES) SELECTBOX */}
                    {warehouses.length > 1 && (
                        <div className="flex flex-col min-w-[200px] flex-1 sm:flex-none">
                            <Listbox
                                value={warehouseId}
                                onChange={(value) => handleWarehouseChange({ target: { value } })}
                            >
                                <div className="relative">
                                    <ListboxButton className="w-full cursor-pointer flex items-center p-3 justify-between rounded-lg border border-slate-200 text-[1rem] bg-white text-slate-900 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors shadow-sm text-left">
                                        <span className="flex items-center gap-3">
                                            <Warehouse className="size-5 shrink-0 text-slate-400" />
                                            <span className="block truncate">
                                                {warehouses.find(w => w.id === warehouseId)?.name || t('common.allWarehouses')}
                                            </span>
                                        </span>
                                        <ChevronsUpDown
                                            aria-hidden="true"
                                            className="size-5 text-gray-400"
                                        />
                                    </ListboxButton>

                                    <ListboxOptions
                                        transition
                                        className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md outline-0 bg-white text-base border border-slate-200 transition duration-100 ease-in data-[closed]:opacity-0 sm:text-sm shadow-lg"
                                    >
                                        {/* Barcha omborlar varianti (Bo'sh qiymat uchun) */}
                                        <ListboxOption
                                            value=""
                                            className="group relative py-2.5 pr-9 pl-3 select-none cursor-pointer text-slate-800 data-[focus]:bg-indigo-600 data-[focus]:text-white outline-hidden"
                                        >
                                            <div className="flex items-center gap-3">
                                                <Warehouse className="size-5 shrink-0 text-gray-400 group-data-[focus]:text-white" />
                                                <span className="block truncate font-normal group-data-[selected]:font-semibold">
                                                    {t('common.allWarehouses')}
                                                </span>
                                            </div>
                                            <span className="absolute inset-y-0 right-0 flex items-center pr-4 text-indigo-600 group-not-data-[selected]:hidden group-data-[focus]:text-white">
                                                <CheckIcon aria-hidden="true" className="size-5" />
                                            </span>
                                        </ListboxOption>

                                        {/* Dinamik omborlar ro'yxati */}
                                        {warehouses.map((w) => (
                                            <ListboxOption
                                                key={w.id}
                                                value={w.id}
                                                className="group relative py-2.5 pr-9 pl-3 select-none cursor-pointer text-slate-800 data-[focus]:bg-indigo-600 data-[focus]:text-white outline-hidden"
                                            >
                                                <div className="flex items-center gap-3">
                                                    <Warehouse className="size-5 shrink-0 text-gray-400 group-data-[focus]:text-white" />
                                                    <span className="block truncate font-normal group-data-[selected]:font-semibold">
                                                        {w.name}
                                                    </span>
                                                </div>

                                                <span className="absolute inset-y-0 right-0 flex items-center pr-4 text-indigo-600 group-not-data-[selected]:hidden group-data-[focus]:text-white">
                                                    <CheckIcon aria-hidden="true" className="size-5" />
                                                </span>
                                            </ListboxOption>
                                        ))}
                                    </ListboxOptions>
                                </div>
                            </Listbox>
                        </div>
                    )}

                </div>

                <button
                    onClick={() => load(true)}
                    className="flex cursor-pointer items-center gap-1.5 text-sm text-slate-500 hover:text-indigo-600 bg-white border border-slate-200 hover:border-indigo-300 rounded-md px-3 py-2 transition-colors shadow-sm"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    {t('common.refresh')}
                </button>
            </div>
            {/* KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-5">
                {kpis.map((kpi) => (
                    <KpiCard key={kpi.label} {...kpi} />
                ))}
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
                {/* Weekly Trend */}
                <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
                    <div className="flex items-center justify-between mb-6">
                        <div>
                            <h3 className="text-base font-semibold text-slate-800">{t('dashboard.recentSales')}</h3>
                            <p className="text-sm text-slate-400 mt-0.5">{t('common.today')} - 7 {t('common.date').toLowerCase()}</p>
                        </div>
                        <div className="w-8 h-8 bg-indigo-50 rounded-lg flex items-center justify-center">
                            <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                            </svg>
                        </div>
                    </div>
                    <ResponsiveContainer width="100%" height={220}>
                        <AreaChart data={data.weekly_trend} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                            <defs>
                                <linearGradient id="colorArea" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.15} />
                                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                            <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                            <YAxis tickFormatter={v => fmt(v)} tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                            <Tooltip content={<CustomTooltip />} />
                            <Area type="monotone" dataKey="amount" stroke="#6366f1" strokeWidth={2.5}
                                fill="url(#colorArea)" dot={{ fill: '#6366f1', r: 3 }} activeDot={{ r: 5 }} />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>

                {/* Top Products */}
                <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
                    <div className="flex items-center justify-between mb-6">
                        <div>
                            <h3 className="text-base font-semibold text-slate-800">{t('dashboard.topProducts')}</h3>
                            <p className="text-sm text-slate-400 mt-0.5">{t('common.thisMonth')}</p>
                        </div>
                        <div className="w-8 h-8 bg-emerald-50 rounded-lg flex items-center justify-center">
                            <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                    d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                            </svg>
                        </div>
                    </div>
                    <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={data.top_products?.slice(0, 7)} layout="vertical" margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
                            <XAxis type="number" tickFormatter={v => fmt(v)} tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                            <YAxis dataKey="name" type="category" width={110} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
                            <Tooltip content={<CustomTooltip />} />
                            <Bar dataKey="revenue" fill="#10b981" radius={[0, 6, 6, 0]} maxBarSize={20} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Monthly 30-day trend */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h3 className="text-base font-semibold text-slate-800">{t('dashboard.monthlyTrend')}</h3>
                        <p className="text-sm text-slate-400 mt-0.5">{t('dashboard.monthlyTrendDesc')}</p>
                    </div>
                    <div className="w-8 h-8 bg-violet-50 rounded-lg flex items-center justify-center">
                        <svg className="w-4 h-4 text-violet-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                    </div>
                </div>
                {data.monthly_trend?.length > 0 ? (
                    <ResponsiveContainer width="100%" height={260}>
                        <ComposedChart data={data.monthly_trend} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                            <defs>
                                <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="#7c3aed" stopOpacity={0.9} />
                                    <stop offset="100%" stopColor="#a78bfa" stopOpacity={0.6} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                            <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 9 }} axisLine={false} tickLine={false} interval={4} />
                            <YAxis tickFormatter={v => fmt(v)} tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                            <Tooltip content={<CustomTooltip />} />
                            <ReferenceLine y={data.monthly_trend.reduce((a, d) => a + d.amount, 0) / data.monthly_trend.length} stroke="#e879f9" strokeDasharray="4 2" strokeWidth={1.5} />
                            <Bar dataKey="amount" fill="url(#barGrad)" radius={[4, 4, 0, 0]} maxBarSize={28} />
                            <Line type="monotone" dataKey="amount" stroke="#7c3aed" strokeWidth={2} dot={false} />
                        </ComposedChart>
                    </ResponsiveContainer>
                ) : (
                    <div className="flex items-center justify-center h-40 text-slate-300 text-sm">{t('common.noData')}</div>
                )}
            </div>

            {/* Cashier Performance + Low Stock row */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
                {/* Kassir samaradorligi */}
                {data.cashier_performance?.length > 0 && (
                    <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
                        <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100">
                            <div className="w-8 h-8 bg-indigo-50 rounded-lg flex items-center justify-center">
                                <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                            </div>
                            <div>
                                <h3 className="text-base font-semibold text-slate-800">{t('dashboard.cashierPerformance')}</h3>
                                <p className="text-sm text-slate-400">{t('dashboard.cashierPerformanceMonth')}</p>
                            </div>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full">
                                <thead>
                                    <tr className="bg-slate-50">
                                        <th className="text-left text-xs font-semibold text-slate-500 uppercase tracking-wider px-6 py-3">#</th>
                                        <th className="text-left text-xs font-semibold text-slate-500 uppercase tracking-wider px-4 py-3">{t('shift.cashier')}</th>
                                        <th className="text-center text-xs font-semibold text-slate-500 uppercase tracking-wider px-4 py-3">{t('sale.title')}</th>
                                        <th className="text-right text-xs font-semibold text-slate-500 uppercase tracking-wider px-6 py-3">{t('common.total')}</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-50">
                                    {data.cashier_performance.map((c, i) => (
                                        <tr key={c.name} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                                            <td className="px-6 py-3.5">
                                                <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${i === 0 ? 'bg-amber-100 text-amber-700' :
                                                    i === 1 ? 'bg-slate-100 text-slate-600' :
                                                        i === 2 ? 'bg-orange-100 text-orange-600' : 'bg-slate-50 text-slate-400'
                                                    }`}>{i + 1}</span>
                                            </td>
                                            <td className="px-4 py-3.5 text-sm font-medium text-slate-800">{c.name}</td>
                                            <td className="px-4 py-3.5 text-center text-sm text-slate-500">{c.count} {t('dashboard.salesCount')}</td>
                                            <td className="px-6 py-3.5 text-right text-sm font-semibold text-emerald-600">{fmt(c.total)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {/* Kam qoldiqli mahsulotlar */}
                {data.low_stock?.length > 0 && (
                    <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
                        <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100">
                            <div className="w-8 h-8 bg-rose-50 rounded-lg flex items-center justify-center">
                                <svg className="w-4 h-4 text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                </svg>
                            </div>
                            <div>
                                <h3 className="text-base font-semibold text-slate-800">{t('dashboard.lowStockProducts')}</h3>
                                <p className="text-sm text-slate-400">{data.low_stock.length} {t('dashboard.lowStockBelowMin')}</p>
                            </div>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full">
                                <thead>
                                    <tr className="bg-slate-50">
                                        <th className="text-left text-xs font-semibold text-slate-500 uppercase tracking-wider px-6 py-3">{t('product.title')}</th>
                                        <th className="text-center text-xs font-semibold text-slate-500 uppercase tracking-wider px-4 py-3">{t('product.stock')}</th>
                                        <th className="text-center text-xs font-semibold text-slate-500 uppercase tracking-wider px-4 py-3">{t('product.minStock')}</th>
                                        <th className="text-center text-xs font-semibold text-slate-500 uppercase tracking-wider px-4 py-3">{t('common.status')}</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-50">
                                    {data.low_stock.slice(0, 8).map((item, i) => (
                                        <tr key={item.product_id} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                                            <td className="px-6 py-3.5">
                                                <span className="text-sm font-medium text-slate-800">{item.name}</span>
                                            </td>
                                            <td className="px-4 py-3.5 text-center">
                                                <span className={`text-sm font-bold ${item.qty <= 0 ? 'text-rose-600' : 'text-amber-600'}`}>
                                                    {item.qty}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3.5 text-center text-sm text-slate-400">{item.min_stock}</td>
                                            <td className="px-4 py-3.5 text-center">
                                                {item.qty <= 0 ? (
                                                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-rose-100 text-rose-700">
                                                        <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />{t('product.outOfStock')}
                                                    </span>
                                                ) : (
                                                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                                                        <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />{t('product.lowStock')}
                                                    </span>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
