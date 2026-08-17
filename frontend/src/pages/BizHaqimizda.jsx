import React from 'react';
import LandingLayout from '../components/LandingLayout';
import { useLang } from '../context/LangContext';
import Reveal from '../components/Reveal';
import { 
  Building2, 
  Target, 
  Rocket, 
  ShieldCheck, 
  ArrowRight, 
  Laptop, 
  ShoppingBag, 
  Warehouse, 
  Users, 
  Banknote, 
  UserCheck, 
  BarChart3, 
  Headphones,
  CheckCircle2,
  Sparkles
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function BizHaqimizda() {
  const { t } = useLang();
  const navigate = useNavigate();

  const services = [
    {
      icon: Laptop,
      title: "ERP platformasini ishlab chiqish",
      desc: "Enterprise Resource Planning — biznes resurslarini yagona tizimda samarali boshqarish."
    },
    {
      icon: ShoppingBag,
      title: "POS savdo tizimlarini yaratish",
      desc: "Point of Sale — tezkor, qulay va xatosiz savdo-kassa jarayonlari."
    },
    {
      icon: Warehouse,
      title: "Ombor va inventar boshqaruvi",
      desc: "Qoldiqlar, kirim-chiqimlar va inventarizatsiya real-vaqt rejimida nazorati."
    },
    {
      icon: Users,
      title: "CRM va mijozlar bilan ishlash",
      desc: "Mijozlar bazasi, sodiqlik dasturlari va mijozlar bilan munosabatlar avtomatizatsiyasi."
    },
    {
      icon: Banknote,
      title: "Moliya va buxgalteriya modullari",
      desc: "Daromad, xarajat, kassa balansi va moliyaviy hisobotlar to'liq shaffofligi."
    },
    {
      icon: UserCheck,
      title: "HR va xodimlar boshqaruvi",
      desc: "Xodimlar davomati, maoshlar hisobi va rollarga ko'ra huquqlarni taqsimlash."
    },
    {
      icon: BarChart3,
      title: "Dashboard va biznes analitikasi",
      desc: "Biznesingizning barcha ko'rsatkichlari bo'yicha vizual grafik va tahlillar."
    },
    {
      icon: Headphones,
      title: "Texnik qo'llab-quvvatlash",
      desc: "Tizimni doimiy rivojlantirish va 24/7 uzluksiz texnik ko'mak."
    }
  ];

  const stats = [
    { number: "2025-yil", label: "Tashkil etilgan", sub: "Bizneslarni raqamlashtirish g'oyasi asosida" },
    { number: "100%", label: "Bulutli va xavfsiz", sub: "Ma'lumotlar shifrlangan muhitda saqlanadi" },
    { number: "24/7", label: "Texnik ko'mak", sub: "Uzluksiz texnik yordam va yangilanishlar" },
    { number: "3+ oy", label: "Muntazam rivojlanish", sub: "Mijozlar ehtiyojidan kelib chiqqan holda" }
  ];

  return (
    <LandingLayout>
      <div className="pt-28 pb-20 bg-slate-50 min-h-screen">
        {/* Hero Section */}
        <div className="max-w-7xl mx-auto px-6 mb-16">
          <div className="text-center max-w-4xl mx-auto">
            <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold uppercase tracking-wider mb-6">
              <Building2 className="w-4 h-4 text-emerald-600" /> E-Code ERP POS
            </span>
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-black text-slate-900 leading-tight mb-6">
              Biz haqimizda
            </h1>
            <p className="text-lg md:text-xl text-slate-700 leading-relaxed font-medium mb-8 bg-white p-8 rounded-3xl border border-slate-200/80 shadow-sm text-left">
              <strong className="text-emerald-700 font-bold">E-Code</strong> — bizneslarni raqamlashtirish g‘oyasi asosida <span className="font-bold text-slate-900">2025-yilda</span> tashkil etilgan zamonaviy ERP va POS tizimlarini ishlab chiquvchi texnologik kompaniya. Kompaniyamiz savdo va xizmat ko‘rsatish sohasidagi korxonalar uchun biznes jarayonlarini avtomatlashtirish, boshqaruvni soddalashtirish hamda ish samaradorligini oshirishga xizmat qiluvchi innovatsion dasturiy yechimlarni yaratadi.
            </p>
          </div>
        </div>

        {/* Feature Overview Grid */}
        <div className="max-w-7xl mx-auto px-6 mb-20">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="bg-white p-8 md:p-10 rounded-3xl border border-slate-200/80 shadow-sm flex flex-col justify-between hover:border-emerald-500/50 transition-all">
              <div>
                <div className="w-12 h-12 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center mb-6">
                  <Rocket className="w-6 h-6" />
                </div>
                <h2 className="text-2xl font-bold text-slate-900 mb-4">Yagona Ekotizim Tizimi</h2>
                <p className="text-slate-600 text-base leading-relaxed">
                  E-Code platformasi ERP va POS texnologiyalarini yagona ekotizimda birlashtirib, savdo, ombor, moliya, xaridlar, CRM, HR va biznes analitikasi kabi muhim jarayonlarni markazlashgan holda boshqarish imkonini beradi. Platformamiz zamonaviy texnologiyalar asosida ishlab chiqilib, turli hajmdagi bizneslarning ehtiyojlariga moslashadigan, xavfsiz va kengaytiriladigan infratuzilmaga ega.
                </p>
              </div>
            </div>

            <div className="bg-white p-8 md:p-10 rounded-3xl border border-slate-200/80 shadow-sm flex flex-col justify-between hover:border-emerald-500/50 transition-all">
              <div>
                <div className="w-12 h-12 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center mb-6">
                  <Target className="w-6 h-6" />
                </div>
                <h2 className="text-2xl font-bold text-slate-900 mb-4">Kompaniyamizning Maqsadi</h2>
                <p className="text-slate-600 text-base leading-relaxed">
                  Kompaniyamizning asosiy maqsadi — tadbirkorlar va korxonalarning raqamli transformatsiyasini qo‘llab-quvvatlash, ularning boshqaruv jarayonlarini soddalashtirish hamda zamonaviy ERP va POS texnologiyalari orqali biznes samaradorligini yangi bosqichga olib chiqishdir. Sotuv faoliyatimiz boshlanganidan buyon platformamiz mijozlar ehtiyojlari asosida muntazam takomillashtirilib, yangi funksiyalar va imkoniyatlar bilan boyitib borilmoqda.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Asosiy faoliyat yo'nalishlarimiz */}
        <div className="max-w-7xl mx-auto px-6 mb-20">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <span className="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-700 bg-emerald-100 px-3 py-1 rounded-full uppercase tracking-wider mb-3">
              <Sparkles className="w-3.5 h-3.5" /> Xizmatlarimiz
            </span>
            <h2 className="text-3xl md:text-4xl font-black text-slate-900">
              Asosiy faoliyat yo‘nalishlarimiz
            </h2>
            <p className="text-slate-600 mt-3 text-base">
              Biznesingizni to'liq avtomatlashtirish uchun majmuaviy yechimlar
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {services.map((s, idx) => {
              const IconComponent = s.icon;
              return (
                <div 
                  key={idx} 
                  className="bg-white p-7 rounded-2xl border border-slate-200/80 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between group"
                >
                  <div>
                    <div className="w-12 h-12 rounded-xl bg-slate-100 group-hover:bg-emerald-600 text-slate-700 group-hover:text-white flex items-center justify-center mb-5 transition-all duration-300">
                      <IconComponent className="w-6 h-6" />
                    </div>
                    <h3 className="text-lg font-bold text-slate-900 mb-2 leading-snug group-hover:text-emerald-600 transition-colors">
                      {s.title}
                    </h3>
                    <p className="text-slate-600 text-xs md:text-sm leading-relaxed">
                      {s.desc}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Stats Section */}
        <div className="max-w-7xl mx-auto px-6 mb-20">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {stats.map((item, idx) => (
              <div key={idx} className="bg-white p-8 rounded-2xl border border-slate-200/80 shadow-sm hover:shadow-md transition-all">
                <div className="text-4xl font-black text-emerald-600 mb-2">{item.number}</div>
                <div className="text-lg font-bold text-slate-900 mb-1">{item.label}</div>
                <div className="text-xs text-slate-500">{item.sub}</div>
              </div>
            ))}
          </div>
        </div>

        {/* CTA */}
        <div className="max-w-4xl mx-auto px-6 text-center">
          <div className="bg-gradient-to-br from-slate-900 to-slate-800 text-white p-10 md:p-14 rounded-3xl shadow-xl relative overflow-hidden">
            <h2 className="text-3xl md:text-4xl font-black mb-4">Biznesingizni birgalikda rivojlantiramiz!</h2>
            <p className="text-slate-300 text-base md:text-lg max-w-2xl mx-auto mb-8">
              Savollaringiz bormi yoki ERP POS tizimini sinab ko'rmoqchimisiz? Biz bilan hoziroq bog'laning.
            </p>
            <button
              onClick={() => navigate('/aloqa')}
              className="px-8 py-4 bg-emerald-500 hover:bg-emerald-600 text-white font-bold rounded-2xl transition-all shadow-lg hover:shadow-emerald-500/20 inline-flex items-center gap-2 cursor-pointer text-base"
            >
              Biz bilan bog'lanish <ArrowRight className="w-5 h-5" />
            </button>
          </div>
        </div>

      </div>
    </LandingLayout>
  );
}
