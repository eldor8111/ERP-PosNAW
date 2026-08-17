import React from 'react';
import LandingLayout from '../components/LandingLayout';
import { useLang } from '../context/LangContext';
import { Newspaper, Calendar, ArrowRight, Sparkles, Tag } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function Yangiliklar() {
  const { t } = useLang();
  const navigate = useNavigate();

  const news = [
    {
      id: 1,
      title: "ERP POS Tizimining yangi 3.0 talqini taqdim etildi",
      date: "01 Avgust, 2026",
      category: "Yangilanish",
      desc: "Yangi talqinda tezkor kassa rejimi, oflayn rejimda ishlash va yangilangan analitika paneli qo'shildi.",
      badge: "Yangi"
    },
    {
      id: 2,
      title: "Telegram Bot bilan avtomatik savdo integratsiyasi",
      date: "25 Iyul, 2026",
      category: "Integratsiya",
      desc: "Endi mijozlar Telegram bot orqali mahsulot tanlab to'lov qilishi va buyurtmalarni avtomatik ERP-ga yuborishi mumkin.",
      badge: "Muhim"
    },
    {
      id: 3,
      title: "Ko'p filialli magazinlar uchun omborlararo o'tkazma va hisobotlar",
      date: "15 Iyul, 2026",
      category: "Xususiyat",
      desc: "Bir nechta filial va omborga ega tadbirkorlar uchun real-vaqt rejimida qoldiqlar harakati boshqaruvi yo'lga qo'yildi.",
      badge: "Xususiyat"
    }
  ];

  return (
    <LandingLayout>
      <div className="pt-28 pb-20 bg-slate-50 min-h-screen">
        {/* Header */}
        <div className="max-w-7xl mx-auto px-6 mb-16">
          <div className="text-center max-w-3xl mx-auto">
            <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold uppercase tracking-wider mb-6">
              <Newspaper className="w-4 h-4" /> So'nggi Yangiliklar
            </span>
            <h1 className="text-4xl md:text-5xl font-black text-slate-900 leading-tight mb-4">
              Tizimimizdagi yangiliklar va <span className="bg-gradient-to-r from-emerald-600 to-blue-500 bg-clip-text text-transparent">muhim e'lonlar</span>
            </h1>
            <p className="text-lg text-slate-600">
              ERP POS tizimi yangilanishlari, yangi funksiyalar va biznesni rivojlantirish bo'yicha maslahatlar
            </p>
          </div>
        </div>

        {/* News Grid */}
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {news.map(item => (
              <div key={item.id} className="bg-white rounded-2xl border border-slate-200/80 shadow-sm hover:shadow-xl transition-all duration-300 flex flex-col justify-between overflow-hidden group">
                <div className="p-8">
                  <div className="flex items-center justify-between gap-2 mb-4">
                    <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-700 bg-emerald-50 px-3 py-1 rounded-lg">
                      <Tag className="w-3.5 h-3.5" /> {item.category}
                    </span>
                    <span className="flex items-center gap-1 text-xs text-slate-400 font-medium">
                      <Calendar className="w-3.5 h-3.5" /> {item.date}
                    </span>
                  </div>
                  <h3 className="text-xl font-bold text-slate-900 mb-3 group-hover:text-emerald-600 transition-colors leading-snug">
                    {item.title}
                  </h3>
                  <p className="text-slate-600 text-sm leading-relaxed mb-6">
                    {item.desc}
                  </p>
                </div>
                <div className="px-8 pb-8 pt-0 mt-auto border-t border-slate-100 flex items-center justify-between">
                  <button
                    onClick={() => navigate('/aloqa')}
                    className="text-xs font-bold text-emerald-600 hover:text-emerald-700 flex items-center gap-1.5 cursor-pointer pt-4"
                  >
                    Batafsil ma'lumot <ArrowRight className="w-4 h-4" />
                  </button>
                  <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 bg-slate-100 text-slate-600 rounded">
                    {item.badge}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </LandingLayout>
  );
}
