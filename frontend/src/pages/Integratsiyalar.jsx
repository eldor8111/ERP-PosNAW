import React from 'react';
import LandingLayout from '../components/LandingLayout';
import Reveal from '../components/Reveal';
import { useSeo } from '../hooks/useSeo';
import PaymeLogo from '../components/PaymeLogo';
import {
  CheckCircle2,
  ShieldCheck,
  Scale,
  CreditCard,
  Sparkles
} from 'lucide-react';

// Imported Integration Assets
import tarozi1Img from '../assets/images/tarozi1.jpg';
import tarozi2Img from '../assets/images/tarozi2.jpg';
import soliqEmblemImg from '../assets/images/soliq_emblem.jpg';
import paymeBlueImg from '../assets/images/payme_blue.png';

export default function Integratsiyalar() {
  useSeo(
    "E-code Integratsiyalar — Soliq va Elektron Tarozilar Integratsiyasi",
    "Soliq Qo'mitasi hamda elektron kassa tarozilari bilan 100% avtomatik integratsiya."
  );

  return (
    <LandingLayout>
      {/* ===== HERO SECTION ===== */}
      <section className="relative pt-32 pb-16 md:pt-40 md:pb-24 overflow-hidden bg-gradient-to-b from-slate-900 via-slate-850 to-[#0A0F1D] text-white">
        {/* Glow & Grid Accents */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(16,185,129,0.15)_0%,transparent_65%)] pointer-events-none" />
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-500/10 blur-[150px] rounded-full pointer-events-none" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.03)_1px,transparent_1px)] bg-[size:40px_40px] pointer-events-none" />

        <div className="max-w-[1400px] mx-auto px-5 relative z-10 text-center">
          <Reveal delay={0.1}>
            <h1 className="text-4xl sm:text-5xl md:text-6xl xl:text-7xl font-extrabold tracking-tight text-white max-w-5xl mx-auto leading-[1.15]">
              Soliq va Tarozilar Bilan{' '}
              <span className="bg-gradient-to-r from-emerald-400 via-blue-300 to-blue-400 bg-clip-text text-transparent">
                Tayyor Integratsiya
              </span>
            </h1>
          </Reveal>

          <Reveal delay={0.2}>
            <p className="mt-6 text-lg sm:text-xl text-slate-300 max-w-3xl mx-auto leading-relaxed">
              Soliq Qo'mitasi fiskal moduli hamda elektron kassa tarozilari bilan 100% avtomatik va xavfsiz ma'lumot almashinuvi.
            </p>
          </Reveal>
        </div>
      </section>

      {/* ===== INTEGRATION CARDS SECTION ===== */}
      <section className="py-16 md:py-24 bg-[#F8FAFC]">
        <div className="max-w-[1400px] mx-auto px-5">

          {/* ===== 1. SOLIQ INTEGRATSIYASI ===== */}
          <Reveal>
            <div className="bg-white rounded-3xl p-8 lg:p-12 border border-slate-200/80 shadow-xl shadow-slate-200/40 mb-16 relative overflow-hidden group hover:border-emerald-500/50 transition-all duration-300">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
                {/* Left Text Info */}
                <div className="lg:col-span-7 space-y-6">
                  <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-blue-50 text-blue-700 text-xs font-bold uppercase tracking-wider">
                    <ShieldCheck className="w-4 h-4 text-blue-600" />
                    <span>Davlat Soliq Qo'mitasi</span>
                  </div>

                  <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
                    Soliq va Fiskalizatsiya Integratsiyasi
                  </h2>

                  <p className="text-slate-600 text-lg leading-relaxed">
                    E-code ERP tizimi O'zbekiston Respublikasi Davlat Soliq Qo'mitasining Online-NKM va Fiskal Modul talablariga 100% javob beradi. Cheklar avtomatik soliq bazasiga uzatiladi.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                    <div className="flex items-start gap-3 p-3.5 rounded-2xl bg-slate-50 border border-slate-100">
                      <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                      <span className="text-sm font-medium text-slate-800">MXIK (IKPU) va Shtrix-kodlar bilan 100% avtomatik moslik</span>
                    </div>
                    <div className="flex items-start gap-3 p-3.5 rounded-2xl bg-slate-50 border border-slate-100">
                      <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                      <span className="text-sm font-medium text-slate-800">QR-kodli Fiskal cheklarni lahzalik bosib chiqarish</span>
                    </div>
                    <div className="flex items-start gap-3 p-3.5 rounded-2xl bg-slate-50 border border-slate-100">
                      <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                      <span className="text-sm font-medium text-slate-800">QQS va Aksiz solig'i hisobini to'g'ri shakllantirish</span>
                    </div>
                    <div className="flex items-start gap-3 p-3.5 rounded-2xl bg-slate-50 border border-slate-100">
                      <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                      <span className="text-sm font-medium text-slate-800">Soliq bazasi bilan xatosiz va xavfsiz ma'lumot almashinuvi</span>
                    </div>
                  </div>
                </div>

                {/* Right Soliq Emblem Image Card */}
                <div className="lg:col-span-5 flex justify-center">
                  <div className="relative p-8 rounded-3xl bg-slate-900 border border-slate-800 shadow-2xl flex flex-col items-center text-center w-full max-w-md">
                    <div className="w-40 h-40 relative flex items-center justify-center p-2 bg-white rounded-2xl border border-slate-200 mb-6 shadow-md">
                      <img
                        src={soliqEmblemImg}
                        alt="Davlat Soliq Qo'mitasi Emblemasi"
                        className="w-full h-full object-contain"
                      />
                    </div>
                    <h3 className="text-xl font-bold text-white mb-2">Davlat Soliq Qo'mitasi</h3>
                    <p className="text-sm text-slate-300">Rasmiy Online-NKM fiskal modul integratsiyasi</p>
                  </div>
                </div>
              </div>
            </div>
          </Reveal>

          {/* ===== 2. ELEKTRON TAROZILAR INTEGRATSIYASI ===== */}
          <Reveal delay={0.1}>
            <div className="bg-white rounded-3xl p-8 lg:p-12 border border-slate-200/80 shadow-xl shadow-slate-200/40 relative overflow-hidden group hover:border-blue-500/50 transition-all duration-300">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">

                {/* Left Scale Showcase Images */}
                <div className="lg:col-span-5 order-2 lg:order-1 flex justify-center">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 w-full max-w-lg">
                    {/* Scale Card 1 */}
                    <div className="p-4 rounded-3xl bg-white border border-slate-200/80 flex flex-col items-center text-center shadow-lg shadow-slate-200/50 hover:shadow-xl hover:border-emerald-400/50 transition-all group">
                      <div className="w-full h-48 rounded-2xl bg-gradient-to-b from-slate-50 to-slate-100/50 p-3 mb-4 flex items-center justify-center overflow-hidden border border-slate-100">
                        <img
                          src={tarozi1Img}
                          alt="Elektron kassa tarozisi"
                          className="max-w-full max-h-full object-contain group-hover:scale-105 transition-transform duration-300"
                        />
                      </div>
                      <span className="text-xs font-extrabold text-slate-800 tracking-tight">Rongta / CAS Shtrix-kodli Tarozi</span>
                    </div>

                    {/* Scale Card 2 */}
                    <div className="p-4 rounded-3xl bg-white border border-slate-200/80 flex flex-col items-center text-center shadow-lg shadow-slate-200/50 hover:shadow-xl hover:border-emerald-400/50 transition-all group">
                      <div className="w-full h-48 rounded-2xl bg-gradient-to-b from-slate-50 to-slate-100/50 p-3 mb-4 flex items-center justify-center overflow-hidden border border-slate-100">
                        <img
                          src={tarozi2Img}
                          alt="Shtrix-kod etiketkali tarozi"
                          className="max-w-full max-h-full object-contain group-hover:scale-105 transition-transform duration-300"
                        />
                      </div>
                      <span className="text-xs font-extrabold text-slate-800 tracking-tight">Elektron Kassa Tarozisi</span>
                    </div>
                  </div>
                </div>

                {/* Right Text Info */}
                <div className="lg:col-span-7 order-1 lg:order-2 space-y-6">
                  <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-emerald-50 text-emerald-700 text-xs font-bold uppercase tracking-wider">
                    <Scale className="w-4 h-4 text-emerald-600" />
                    <span>Savdo Uskunalari</span>
                  </div>

                  <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
                    Elektron Kassa Tarozilari Integratsiyasi
                  </h2>

                  <p className="text-slate-600 text-lg leading-relaxed">
                    Supermarket, meva-sabzavot, go'sht va ulgurji do'konlar uchun barcha rusumdagi tarozilar (Rongta, CAS, MassK va b.) bilan lahzalik ulanish.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                    <div className="flex items-start gap-3 p-3.5 rounded-2xl bg-slate-50 border border-slate-100">
                      <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                      <span className="text-sm font-medium text-slate-800">Shtrix-kodli mahsulot etiketkasini (label) avtomatik bosish</span>
                    </div>
                    <div className="flex items-start gap-3 p-3.5 rounded-2xl bg-slate-50 border border-slate-100">
                      <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                      <span className="text-sm font-medium text-slate-800">RS-232, Ethernet va Wi-Fi tarmoq interfeysi orqali ulanish</span>
                    </div>
                    <div className="flex items-start gap-3 p-3.5 rounded-2xl bg-slate-50 border border-slate-100">
                      <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                      <span className="text-sm font-medium text-slate-800">Vaznni to'g'ridan-to'g'ri POS kassaga xatoliksiz uzatish</span>
                    </div>
                    <div className="flex items-start gap-3 p-3.5 rounded-2xl bg-slate-50 border border-slate-100">
                      <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                      <span className="text-sm font-medium text-slate-800">Ombordagi narxlarni taroziga bir tugma orqali yangilash</span>
                    </div>
                  </div>
                </div>

              </div>
            </div>
          </Reveal>

        </div>
      </section>
    </LandingLayout>
  );
}
