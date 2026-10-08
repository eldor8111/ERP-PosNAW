import React from 'react';
import LandingLayout from '../components/LandingLayout';
import { ShieldCheck, Lock, Eye, FileText } from 'lucide-react';
import { useSeo } from '../hooks/useSeo';

export default function Privacy() {
  useSeo({
    title: "Maxfiylik Siyosati - E-Code",
    description: "E-Code platformasining maxfiylik siyosati. Biz foydalanuvchilarimiz ma'lumotlarini qanday saqlashimiz va himoya qilishimiz haqida batafsil ma'lumot.",
  });

  const sections = [
    {
      icon: <ShieldCheck className="w-8 h-8 text-blue-500" />,
      title: "1. Umumiy qoidalar",
      content: "Ushbu Maxfiylik Siyosati E-Code platformasi (keyingi o'rinlarda «Tizim») foydalanuvchilarining shaxsiy ma'lumotlarini to'plash, saqlash, foydalanish va himoya qilish tartibini belgilaydi. Tizimdan foydalanish orqali siz ushbu siyosat shartlariga to'liq rozi bo'lasiz."
    },
    {
      icon: <Eye className="w-8 h-8 text-blue-500" />,
      title: "2. Qanday ma'lumotlarni yig'amiz?",
      content: "Biz faqatgina xizmat ko'rsatish uchun zarur bo'lgan ma'lumotlarni yig'amiz. Bunga sizning ismingiz, telefon raqamingiz, elektron pochta manzilingiz va korxona ma'lumotlaringiz kiradi. Shuningdek, tizimdan foydalanish sifatini oshirish maqsadida texnik ma'lumotlar (IP manzil, brauzer turi) avtomatik ravishda yig'ilishi mumkin."
    },
    {
      icon: <Lock className="w-8 h-8 text-blue-500" />,
      title: "3. Ma'lumotlardan qanday foydalanamiz?",
      content: "Sizning ma'lumotlaringiz faqat quyidagi maqsadlarda foydalaniladi: Tizim xizmatlarini taqdim etish va takomillashtirish; Texnik yordam ko'rsatish; Yangilanishlar va muhim xabarlar haqida sizni xabardor qilish; Xavfsizlikni ta'minlash va firibgarlikning oldini olish."
    },
    {
      icon: <FileText className="w-8 h-8 text-blue-500" />,
      title: "4. Ma'lumotlarni himoya qilish",
      content: "Biz shaxsiy ma'lumotlaringizni xavfsiz saqlash uchun zamonaviy shifrlash va xavfsizlik choralarini qo'llaymiz. Sizning ma'lumotlaringiz uchinchi shaxslarga sotilmaydi yoki ularga ruxsatsiz oshkor etilmaydi, qonun hujjatlarida nazarda tutilgan hollar bundan mustasno."
    }
  ];

  return (
    <LandingLayout>
      <div className="pt-32 pb-20 min-h-screen bg-slate-50 relative overflow-hidden">
        {/* Background Gradients */}
        <div className="absolute top-0 left-0 w-full h-[500px] bg-gradient-to-br from-blue-600/10 via-blue-400/5 to-transparent -z-10" />
        <div className="absolute -top-[300px] -right-[200px] w-[600px] h-[600px] rounded-full bg-blue-500/10 blur-[120px] -z-10" />
        <div className="absolute top-[20%] -left-[100px] w-[400px] h-[400px] rounded-full bg-blue-400/10 blur-[100px] -z-10" />

        <div className="max-w-[800px] mx-auto px-6 relative z-10">
          <div className="text-center mb-16">
            <div className="inline-flex items-center justify-center p-3 bg-blue-100/50 rounded-2xl mb-6 shadow-sm border border-blue-200/50">
              <ShieldCheck className="w-8 h-8 text-blue-600" />
            </div>
            <h1 className="text-4xl md:text-5xl font-black text-slate-900 mb-6 tracking-tight">
              Maxfiylik Siyosati
            </h1>
            <p className="text-lg text-slate-600 leading-relaxed max-w-2xl mx-auto">
              Biz sizning ma'lumotlaringiz xavfsizligiga jiddiy e'tibor qaratamiz. Ushbu hujjatda biz qanday qilib sizning ma'lumotlaringizni himoya qilishimiz tushuntirilgan.
            </p>
          </div>

          <div className="space-y-8">
            {sections.map((section, index) => (
              <div 
                key={index}
                className="bg-white rounded-3xl p-8 md:p-10 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-slate-100 hover:shadow-[0_8px_30px_rgba(37,99,235,0.08)] transition-all duration-300 relative overflow-hidden group"
              >
                <div className="absolute top-0 left-0 w-1.5 h-0 bg-blue-500 transition-all duration-300 group-hover:h-full" />
                
                <div className="flex flex-col md:flex-row gap-6">
                  <div className="shrink-0">
                    <div className="w-16 h-16 rounded-2xl bg-blue-50 flex items-center justify-center border border-blue-100">
                      {section.icon}
                    </div>
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold text-slate-900 mb-4">{section.title}</h2>
                    <p className="text-slate-600 leading-relaxed text-[17px]">
                      {section.content}
                    </p>
                  </div>
                </div>
              </div>
            ))}

            <div className="bg-gradient-to-br from-blue-600 to-blue-800 rounded-3xl p-8 md:p-10 text-center text-white mt-12 shadow-xl shadow-blue-900/20">
              <h3 className="text-2xl font-bold mb-4">Savollaringiz bormi?</h3>
              <p className="text-blue-100 mb-6 max-w-lg mx-auto">
                Maxfiylik siyosatimiz bo'yicha savollaringiz bo'lsa, biz bilan bog'lanishdan tortinmang. Biz sizga yordam berishdan doim xursandmiz.
              </p>
              <a 
                href="/aloqa" 
                className="inline-flex items-center justify-center bg-white text-blue-700 font-bold px-8 py-3.5 rounded-xl hover:bg-blue-50 transition-colors shadow-sm"
              >
                Biz bilan bog'lanish
              </a>
            </div>
          </div>
        </div>
      </div>
    </LandingLayout>
  );
}
