import { ChevronLeft } from 'lucide-react';
import React from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';

const NotFound = () => {
    const navigate = useNavigate()

    // Sahifani yangilash funksiyasi (Muammoni qayta tekshirish uchun)
    const handleRefresh = () => {
        window.location.reload();
    };

    return (
        <div className="relative min-h-screen w-full flex items-center justify-center bg-slate-950 overflow-hidden font-sans select-none">

            {/* 1. Background Dizayn Elementlari: To'rsimon fon va neon yorug'liklar */}
            <div className="absolute inset-0 opacity-[0.07] pointer-events-none bg-[linear-gradient(to_right,#ffffff_1px,transparent_1px),linear-gradient(to_bottom,#ffffff_1px,transparent_1px)] bg-[size:3rem_3rem]"></div>

            {/* Orqa fondagi chiroyli gradient nurlar */}
            <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-[120px] pointer-events-none"></div>
            <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-violet-500/10 rounded-full blur-[120px] pointer-events-none"></div>

            {/* 2. Asosiy Kontent Bloki */}
            <div className="relative z-10 max-w-xl mx-auto px-6 py-12 text-center flex flex-col items-center">

                {/* Vizual 404 llustratsiyasi (Faqat Tailwind klasslarida) */}
                <div className="relative mb-8 flex items-center justify-center">
                    {/* Pulsatsiya qiluvchi tashqi halqalar */}
                    <div className="absolute w-44 h-44 bg-indigo-500/5 rounded-full animate-ping duration-3000"></div>
                    <div className="absolute w-56 h-56 bg-violet-500/5 rounded-full animate-pulse"></div>

                    {/* Markaziy Neon Blok */}
                    <div className="relative w-36 h-36 rounded-3xl bg-gradient-to-br from-indigo-500/10 to-violet-500/10 border border-indigo-500/20 backdrop-blur-md flex flex-col items-center justify-center shadow-2xl shadow-indigo-500/5">
                        <span className="text-6xl font-black bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 tracking-tighter">
                            404
                        </span>
                        <div className="absolute -bottom-3 px-3 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 uppercase tracking-widest">
                            Xatolik
                        </div>
                    </div>
                </div>

                {/* Matnlar */}
                <h1 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight mb-3">
                    Sahifa topilmadi
                </h1>
                <p className="text-base text-slate-400 max-w-md mb-8 leading-relaxed">
                    Kechirasiz, siz qidirayotgan sahifa mavjud emas, o'chirilgan yoki manzili o'zgartirilgan bo'lishi mumkin.
                </p>

                {/* 3. Harakatlar tugmalari (Action Buttons) */}
                <div className="flex flex-col sm:flex-row items-center justify-center gap-4 w-full sm:w-auto">
                    {/* Bosh sahifaga qaytish */}
                    <Link onClick={() => navigate(-1)}
                        className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3.5 text-sm font-semibold text-white bg-gradient-to-r from-indigo-600 to-violet-600 rounded-xl shadow-lg shadow-indigo-600/15 hover:from-indigo-500 hover:to-violet-500 hover:shadow-indigo-500/20 active:scale-[0.98] transition-all duration-200 cursor-pointer border border-indigo-500/20 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
                    >
                        <ChevronLeft size={20} />
                        Ortga qaytish
                    </Link>

                    {/* Qayta urinib ko'rish */}
                    <button
                        onClick={handleRefresh}
                        className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3.5 text-sm font-semibold text-slate-300 bg-slate-900/80 border border-slate-800 rounded-xl hover:bg-slate-800 hover:text-white active:scale-[0.98] transition-all duration-200 backdrop-blur-sm cursor-pointer"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                        </svg>
                        Sahifani yangilash
                    </button>
                </div>

                {/* 4. Mini Footer yoki Yordam qismi */}
                <div className="mt-12 text-xs text-slate-600 tracking-wide">
                    Tizim kodi: <span className="font-mono text-indigo-400/60">ERR_ROUTE_NOT_FOUND</span>
                </div>

            </div>
        </div>
    );
};

export default NotFound;