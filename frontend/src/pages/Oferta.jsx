import React, { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import LandingLayout from '../components/LandingLayout';
import { useSeo } from '../hooks/useSeo';
import {
  FileText,
  ShieldCheck,
  CreditCard,
  RotateCcw,
  AlertTriangle,
  Lock,
  CheckCircle2,
  Download,
  Building,
  Phone,
  Mail,
  Send,
  HelpCircle,
} from 'lucide-react';

export default function Oferta() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlLang = searchParams.get('lang');
  const [lang, setLang] = useState(urlLang === 'ru' ? 'ru' : 'uz');

  useEffect(() => {
    if (urlLang === 'ru' || urlLang === 'uz') {
      setLang(urlLang);
    }
  }, [urlLang]);

  const switchLang = (newLang) => {
    setLang(newLang);
    setSearchParams(newLang === 'ru' ? { lang: 'ru' } : {});
  };

  useSeo({
    title: lang === 'ru'
      ? "Публичная оферта и безопасность платежей - E-Code"
      : "Ommaviy oferta va to'lovlar xavfsizligi - E-Code",
    description: lang === 'ru'
      ? "Публичная оферта на использование платформы E-Code ERP, правила оплаты, безопасность платежей и меры противодействия мошенничеству (Antifraud)."
      : "E-Code ERP platformasidan foydalanish bo'yicha ommaviy oferta, to'lov tartibi, to'lov xavfsizligi va firibgarlikning oldini olish choralari.",
  });

  return (
    <LandingLayout>
      <div className="pt-28 pb-20 min-h-screen bg-slate-50 relative overflow-hidden">
        {/* Orqa fon bezaklari */}
        <div className="absolute top-0 left-0 w-full h-[450px] bg-gradient-to-br from-blue-600/10 via-sky-400/5 to-transparent -z-10" />
        <div className="absolute -top-[250px] -right-[150px] w-[500px] h-[500px] rounded-full bg-blue-500/10 blur-[120px] -z-10" />

        <div className="max-w-5xl mx-auto px-4 sm:px-6 relative z-10">
          {/* Header */}
          <div className="text-center mb-10">
            <div className="inline-flex items-center gap-2 p-2 px-4 bg-blue-50 rounded-full mb-4 shadow-sm border border-blue-100">
              <FileText className="w-5 h-5 text-blue-600" />
              <span className="text-xs sm:text-sm font-bold text-blue-700 uppercase tracking-wider">
                {lang === 'ru' ? 'Официальный документ' : 'Rasmiy hujjat'}
              </span>
            </div>

            <h1 className="text-3xl sm:text-4xl md:text-5xl font-black text-slate-900 mb-4 tracking-tight">
              {lang === 'ru' ? 'Публичная оферта' : 'Ommaviy oferta'}
            </h1>
            <p className="text-base sm:text-lg text-slate-600 max-w-2xl mx-auto mb-6">
              {lang === 'ru'
                ? 'Договор публичной оферты на оказание услуг сервиса E-Code ERP, порядок расчётов, безопасность платежей и защита от мошеннических операций.'
                : "E-Code ERP dasturiy platformasidan foydalanish bo'yicha shartnoma, to'lov tartibi, to'lov xavfsizligi va firibgarlikning oldini olish choralari."}
            </p>

            {/* Tilni almashtirish tugmalari va PDF */}
            <div className="flex flex-wrap items-center justify-center gap-3">
              <div className="inline-flex p-1 bg-white rounded-xl border border-slate-200 shadow-sm">
                <button
                  type="button"
                  onClick={() => switchLang('uz')}
                  className={`px-4 py-1.5 rounded-lg text-sm font-bold transition-all ${
                    lang === 'uz' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:text-blue-600'
                  }`}
                >
                  🇺🇿 O'zbekcha
                </button>
                <button
                  type="button"
                  onClick={() => switchLang('ru')}
                  className={`px-4 py-1.5 rounded-lg text-sm font-bold transition-all ${
                    lang === 'ru' ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:text-blue-600'
                  }`}
                >
                  🇷🇺 Русский
                </button>
              </div>

              <a
                href="/oferta.pdf"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm font-semibold text-slate-700 hover:bg-slate-100 hover:text-blue-600 transition-colors shadow-sm"
              >
                <Download className="w-4 h-4 text-blue-600" />
                <span>PDF formatida yuklab olish</span>
              </a>
            </div>
          </div>

          {/* Antifraud Alert Banner (Bank tekshiruvi uchun muhim xabarnoma) */}
          <div className="mb-8 p-5 sm:p-6 bg-gradient-to-r from-emerald-50 via-teal-50 to-blue-50 border-2 border-emerald-300/80 rounded-2xl shadow-sm">
            <div className="flex items-start gap-4">
              <div className="p-2.5 bg-emerald-600 text-white rounded-xl shadow-sm shrink-0">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base sm:text-lg font-bold text-slate-900 mb-1">
                  {lang === 'ru'
                    ? 'Безопасность платежей и контроль рисков (PCI DSS / Antifraud)'
                    : "To'lovlar xavfsizligi va xavflarni nazorat qilish (PCI DSS / Antifraud)"}
                </h3>
                <p className="text-sm text-slate-700 leading-relaxed">
                  {lang === 'ru'
                    ? 'Сервис E-Code реализует комплексные меры противодействия мошенническим операциям в партнёрстве с банками-эквайерами (включая АО «UZUM BANK»). Все данные банковских карт защищены стандартом PCI DSS, подтверждаются 3D-Secure / OTP, и не хранятся на серверах Сервиса. Подробности — в Разделе 7 настоящей Оферты.'
                    : "E-Code xizmati ekvayer-banklar (jumladan «UZUM BANK» AJ) bilan hamkorlikda firibgarlik operatsiyalarini cheklash va nazorat qilish choralarini to'liq tatbiq etadi. Barcha bank karta ma'lumotlari PCI DSS standarti bilan himoyalangan, 3D-Secure / OTP orqali tasdiqlanadi va serverlarimizda saqlanmaydi. Batafsil — ushbu Ofertaning 7-bo'limida."}
                </p>
              </div>
            </div>
          </div>

          {/* Content Document */}
          <div className="bg-white rounded-3xl p-6 sm:p-10 shadow-sm border border-slate-200 text-slate-800 leading-relaxed space-y-10">
            {lang === 'ru' ? <OfertaContentRu /> : <OfertaContentUz />}

            {/* Rekvizitlar */}
            <div className="pt-8 border-t border-slate-200">
              <div className="flex items-center gap-3 mb-6">
                <div className="p-2 bg-blue-100 text-blue-700 rounded-xl">
                  <Building className="w-6 h-6" />
                </div>
                <h2 className="text-xl sm:text-2xl font-bold text-slate-900">
                  {lang === 'ru' ? '10. Реквизиты Исполнителя и контактные данные' : "10. Ijrochi rekvizitlari va aloqa ma'lumotlari"}
                </h2>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 bg-slate-50 p-6 rounded-2xl border border-slate-200">
                <div className="space-y-2 text-sm text-slate-700">
                  <p className="font-bold text-base text-slate-900">E-Code ERP Platformasi</p>
                  <p><span className="font-semibold">{lang === 'ru' ? 'Исполнитель' : 'Ijrochi'}:</span> YaTT / ИП UMAR SHUXRATOV SHOVKAT O'G'LI</p>
                  <p><span className="font-semibold">{lang === 'ru' ? 'Сервис' : 'Xizmat'}:</span> e-code.uz / savdo.e-code.uz</p>
                  <p><span className="font-semibold">{lang === 'ru' ? 'Деятельность' : 'Faoliyat turi'}:</span> Dasturiy ta'minot ishlab chiqish, ERP va POS bulutli xizmatlari</p>
                </div>

                <div className="space-y-3 text-sm text-slate-700">
                  <div className="flex items-center gap-2">
                    <Phone className="w-4 h-4 text-blue-600" />
                    <span>+998 88 911 81 71 / +998 90 939 70 79</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Mail className="w-4 h-4 text-blue-600" />
                    <a href="mailto:ecode.uz@gmail.com" className="text-blue-600 hover:underline">
                      ecode.uz@gmail.com
                    </a>
                  </div>
                  <div className="flex items-center gap-2">
                    <Send className="w-4 h-4 text-blue-600" />
                    <a href="https://t.me/ecode_uz" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                      @ecode_uz (Telegram qo'llab-quvvatlash)
                    </a>
                  </div>
                  <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 text-xs text-amber-900">
                    <strong>{lang === 'ru' ? 'Канал сообщений о подозрительных операциях (Antifraud):' : 'Shubhali operatsiyalar bo\'yicha murojaat kanali (Antifraud):'}</strong><br />
                    Email: <span className="font-mono text-blue-700">antifraud@e-code.uz</span> / <span className="font-mono text-blue-700">ecode.uz@gmail.com</span><br />
                    {lang === 'ru' ? 'Срок рассмотрения обращений — до 24 часов.' : 'Murojaatlarni ko\'rib chiqish muddati — 24 soatgacha.'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </LandingLayout>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// RUSSIAN VERSION
// ─────────────────────────────────────────────────────────────────────────────
function OfertaContentRu() {
  return (
    <div className="space-y-8 text-slate-700 text-sm sm:text-base leading-relaxed">
      <section className="space-y-3">
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900">1. Общие положения</h2>
        <p>
          1.1. Настоящий документ является официальным предложением (публичной офертой в соответствии со статьей 369 Гражданского кодекса Республики Узбекистан) Исполнителя и содержит все существенные условия предоставления доступа к платформе E-Code ERP (далее — «Сервис»).
        </p>
        <p>
          1.2. Акцептом настоящей Оферты признается совершение Пользователем любого из следующих действий: регистрация учетной записи на сайте https://e-code.uz или https://savdo.e-code.uz, оплата тарифа, либо фактическое использование возможностей Сервиса.
        </p>
        <p>
          1.3. Совершая акцепт, Пользователь подтверждает, что ознакомлен, полностью и безоговорочно согласен со всеми положениями настоящей Оферты, Политикой конфиденциальности и условиями обслуживания.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900">2. Предмет договора</h2>
        <p>
          2.1. Исполнитель предоставляет Пользователю доступ к облачному программному комплексу E-Code ERP (включая модули POS-терминала, складского учета, CRM, аналитики и сопутствующих интеграций) на условиях простой (неисключительной) лицензии в соответствии с выбранным тарифным планом.
        </p>
        <p>
          2.2. Сервис предоставляется по модели SaaS («программное обеспечение как услуга») через веб-интерфейс без необходимости установки ПО на серверное оборудование Пользователя.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900">3. Регистрация и безопасность учетной записи</h2>
        <p>
          3.1. Для доступа к Сервису Пользователь проходит процедуру регистрации, создавая уникальную учетную запись и пароль.
        </p>
        <p>
          3.2. Пользователь несет полную ответственность за сохранность конфиденциальности своих учетных данных и за любые действия, совершенные под его аккаунтом.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900">4. Права и обязанности Сторон</h2>
        <p>
          4.1. <strong>Исполнитель обязуется:</strong> обеспечивать бесперебойную доступность Сервиса (за исключением периодов планового технического обслуживания), сохранять конфиденциальность коммерческих данных Пользователя, оказывать техническую поддержку.
        </p>
        <p>
          4.2. <strong>Пользователь обязуется:</strong> своевременно оплачивать доступ к Сервису согласно тарифам, не использовать Сервис для противоправной деятельности, не нарушать интеллектуальные права Исполнителя.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900">5. Тарифы и условия обслуживания</h2>
        <p>
          5.1. Стоимость доступа к Сервису определяется тарифами, опубликованными в интерфейсе платформы в разделе «Тарифы».
        </p>
        <p>
          5.2. Исполнитель вправе в одностороннем порядке изменять тарифы, предварительно уведомив Пользователей не менее чем за 10 календарных дней через интерфейс Сервиса или по электронной почте.
        </p>
      </section>

      {/* РАЗДЕЛ 6: ПОРЯДОК ОПЛАТЫ */}
      <section className="space-y-3 p-5 sm:p-6 bg-slate-50 rounded-2xl border border-slate-200">
        <div className="flex items-center gap-2 text-blue-700 font-bold text-lg">
          <CreditCard className="w-5 h-5" />
          <h2>6. Порядок оплаты и расчётов</h2>
        </div>
        <p>
          6.1. <strong>Способы оплаты:</strong> Оплата тарифных планов и дополнительных модулей осуществляется безналичным расчетом через подключенные платежные системы и интернет-эквайринг (включая банковские карты Uzcard, Humo, Visa, Mastercard, а также через сервис АО «UZUM BANK»).
        </p>
        <p>
          6.2. <strong>Пошаговый процесс оплаты:</strong> Пользователь выбирает тариф в панели управления, нажимает кнопку «Оплатить», перенаправляется на защищенную платежную страницу процессингового центра / Банка-эквайера, где вводит реквизиты карты и подтверждает платеж с помощью одноразового SMS-пароля (OTP).
        </p>
        <p>
          6.3. <strong>Валюта расчетов:</strong> Валютой платежей на территории Республики Узбекистан является узбекский сум (UZS).
        </p>
        <p>
          6.4. <strong>Фискальный чек:</strong> После успешного завершения платежа формируется электронный фискальный чек с QR-кодом, соответствующий требованиям налогового законодательства РУз, который направляется Пользователю.
        </p>
        <p>
          6.5. <strong>Срок активации:</strong> Активация тарифа и продление подписки производятся автоматически в режиме реального времени сразу после получения подтверждения об успешной транзакции от Банка-эквайера.
        </p>
      </section>

      {/* РАЗДЕЛ 7: АНТИФРОД И БЕЗОПАСНОСТЬ (КЛЮЧЕВОЙ РАЗДЕЛ ДЛЯ UZUM BANK) */}
      <section className="space-y-4 p-5 sm:p-7 bg-amber-50/70 border-2 border-amber-300/80 rounded-2xl">
        <div className="flex items-center gap-2 text-amber-900 font-black text-lg sm:text-xl">
          <Lock className="w-6 h-6 text-amber-700" />
          <h2>7. Безопасность платежей и меры противодействия мошенничеству (Контроль рисков)</h2>
        </div>

        <div className="space-y-3 text-slate-800">
          <p>
            Настоящий раздел регламентирует способы ограничения и осуществления контроля рисков мошеннических операций, применяя возможности Банка-эквайера (включая АО «UZUM BANK») по борьбе с мошенническими операциями, путем реализации ограничений, предусмотренных Договором интернет-эквайринга:
          </p>

          <ul className="space-y-3 list-none pl-0">
            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">п. 7.1.</span>
              <span>
                <strong>Невмешательство в данные банковских карт:</strong> Данные банковских карт (номер карты, срок действия, CVV/CVC-код) не попадают в информационные системы Сервиса E-Code. Ввод реквизитов карты осуществляется Пользователем исключительно на защищенной платежной странице сертифицированного процессингового центра Банка-эквайера. Сервис E-Code не видит, не получает, не обрабатывает и не сохраняет данные банковских карт Пользователей.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">п. 7.2.</span>
              <span>
                <strong>Стандарты безопасности передачи данных:</strong> Платёжный оператор и Банк-эквайер работают в строгом соответствии с международным стандартом безопасности индустрии платежных карт PCI DSS. Передача всей информации по защищенным каналам связи шифруется с использованием протоколов TLS (Transport Layer Security) актуальных версий с длиной ключа не менее 256 бит.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">п. 7.3.</span>
              <span>
                <strong>Двухфакторная аутентификация (3D-Secure / OTP):</strong> Каждая платежная операция в обязательном порядке подтверждается вводом одноразового SMS-кода (OTP — One Time Password), направляемого банком-эмитентом на доверенный номер телефона держателя банковской карты, что исключает возможность несанкционированного списания денежных средств третьими лицами.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">п. 7.4.</span>
              <span>
                <strong>Реализация ограничений и лимитов Договора ИЭ:</strong> Исполнитель принимает все ограничения, предусмотренные Договором интернет-эквайринга, и в полной мере использует возможности Банка-эквайера по мониторингу и предотвращению подозрительных операций. Лимиты по суммам разовой операции, суточные и месячные ограничения по карте, а также приостановка либо отклонение операций с признаками подозрительности применяются на стороне Банка и платежной системы. Операция, отклоненная Банком, на стороне Сервиса не исполняется — тариф зачисляется только после окончательного подтверждения успешности платежа. Любые запросы Банка о проверке, приостановке или отмене подозрительной операции исполняются Исполнителем безусловно.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">п. 7.5.</span>
              <span>
                <strong>Внутренний аудит и мониторинг транзакций:</strong> На стороне Сервиса E-Code ведется непрерывный электронный журнал по каждому платежному заказу и транзакции (включающий дату и точное время, сумму, статус, уникальный номер транзакции, идентификатор аккаунта и IP-адрес инициатора). Указанный журнал незамедлительно предоставляется по официальному запросу Банка-эквайера или правоохранительных органов.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">п. 7.6.</span>
              <span>
                <strong>Блокировка при выявлении признаков мошенничества:</strong> При обнаружении попыток использования скомпрометированных карт, множественных неудачных попыток оплат, аномальной активности или при получении уведомления от антифрод-системы Банка, учетная запись нарушителя подлежит немедленной блокировке до выяснения обстоятельств.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">п. 7.7.</span>
              <span>
                <strong>Сроки рассмотрения инцидентов:</strong> Любые обращения Пользователей или Банка относительно спорных или подозрительных транзакций рассматриваются специалистами Сервиса в приоритетном порядке в течение не более 24 (двадцати четырех) часов с момента поступления.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">п. 7.8.</span>
              <span>
                <strong>Выделенный канал антифрод-оповещения:</strong> Для оперативного информирования о подозрительных операциях или несанкционированных списаниях действует специальный канал связи: электронная почта <code className="bg-white px-2 py-0.5 rounded border border-amber-300 font-mono text-amber-900">antifraud@e-code.uz</code> и горячая линия службы поддержки <code className="bg-white px-2 py-0.5 rounded border border-amber-300 font-mono text-amber-900">+998 88 911 81 71</code>.
              </span>
            </li>
          </ul>
        </div>
      </section>

      {/* РАЗДЕЛ 8: ПОРЯДОК ВОЗВРАТА */}
      <section className="space-y-3 p-5 sm:p-6 bg-slate-50 rounded-2xl border border-slate-200">
        <div className="flex items-center gap-2 text-blue-700 font-bold text-lg">
          <RotateCcw className="w-5 h-5" />
          <h2>8. Порядок возврата денежных средств</h2>
        </div>
        <p>
          8.1. <strong>Основания для возврата:</strong> Возврат денежных средств возможен в случае ошибочного повторного списания, сбоя в процессе проведения транзакции, либо в случае невозможности предоставления доступа к Сервису по вине Исполнителя в течение более 48 часов подряд.
        </p>
        <p>
          8.2. <strong>Порядок обращения:</strong> Для оформления возврата Пользователь направляет письменное заявление на электронную почту <code className="font-mono text-blue-700">ecode.uz@gmail.com</code> с указанием Ф.И.О., номера телефона, даты и суммы платежа, а также описанием причины возврата.
        </p>
        <p>
          8.3. <strong>Срок рассмотрения:</strong> Заявление о возврате рассматривается Исполнителем в течение 3 (трех) рабочих дней с момента получения.
        </p>
        <p>
          8.4. <strong>Срок и способ выплаты:</strong> Возврат денежных средств осуществляется исключительно на ту же банковскую карту, с которой была произведена оплата, в срок до 10 (десяти) банковских дней (фактический срок зачисления зависит от регламента банка-эмитента карты).
        </p>
        <p>
          8.5. <strong>Отсутствие комиссий:</strong> Комиссия за осуществление возврата денежных средств с Пользователя не удерживается.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900">9. Срок действия и порядок разрешения споров</h2>
        <p>
          9.1. Настоящая Оферта вступает в силу с момента ее публикации на сайте https://e-code.uz и действует бессрочно до момента ее отзыва Исполнителем.
        </p>
        <p>
          9.2. Все споры и разногласия разрешаются путем конструктивных переговоров. При недостижении согласия спор передается на рассмотрение в суд по месту нахождения Исполнителя в соответствии с законодательством Республики Узбекистан.
        </p>
      </section>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// UZBEK VERSION
// ─────────────────────────────────────────────────────────────────────────────
function OfertaContentUz() {
  return (
    <div className="space-y-8 text-slate-700 text-sm sm:text-base leading-relaxed">
      <section className="space-y-3">
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900">1. Umumiy qoidalar</h2>
        <p>
          1.1. Ushbu hujjat Ijrochining rasmiy taklifi (O'zbekiston Respublikasi Fuqarolik kodeksining 369-moddasiga muvofiq ommaviy oferta) bo'lib, E-Code ERP platformasidan (keyingi o'rinlarda «Xizmat») foydalanish bo'yicha barcha muhim shartlarni o'z ichiga oladi.
        </p>
        <p>
          1.2. Foydalanuvchi tomonidan quyidagi harakatlardan biri bajarilishi ushbu Ofertani to'liq va so'zsiz qabul qilish (aksept) hisoblanadi: https://e-code.uz yoki https://savdo.e-code.uz saytida ro'yxatdan o'tish, tarif rejasiga to'lov qilish yoki Xizmat imkoniyatlaridan amalda foydalanish.
        </p>
        <p>
          1.3. Ofertani aksept qilish orqali Foydalanuvchi ushbu shartnoma shartlari, Maxfiylik siyosati va xizmat ko'rsatish qoidalari bilan to'liq tanishganligini va ularga so'zsiz roziligini tasdiqlaydi.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900">2. Shartnoma predmeti</h2>
        <p>
          2.1. Ijrochi Foydalanuvchiga E-Code ERP bulutli dasturiy majmuasiga (POS-terminal, ombor hisobi, savdo, CRM, tahlil va tegishli integratsiya modullari) tanlangan tarif rejasi doirasida oddiy (mutlaq bo'lmagan) litsenziya asosida kirish huquqini taqdim etadi.
        </p>
        <p>
          2.2. Xizmat SaaS («xizmat sifatida dasturiy ta'minot») modeli asosida veb-brauzer orqali ko'rsatiladi, Foydalanuvchi qurilmasiga qo'shimcha server dasturlarini o'rnatish talab etilmaydi.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900">3. Ro'yxatdan o'tish va hisob xavfsizligi</h2>
        <p>
          3.1. Xizmatdan foydalanish uchun Foydalanuvchi ro'yxatdan o'tadi va o'zining yagona hisob yozuvi hamda maxfiy parolini yaratadi.
        </p>
        <p>
          3.2. Foydalanuvchi o'z kirish ma'lumotlarining maxfiyligini ta'minlash va o'z hisobi ostida amalga oshirilgan barcha harakatlar uchun to'liq javobgardir.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900">4. Tomonlarning huquq va majburiyatlari</h2>
        <p>
          4.1. <strong>Ijrochi majburiyatlari:</strong> Xizmatning uzluksiz ishlashini ta'minlash (rejaviy texnik profilaktika ishlari bundan mustasno), Foydalanuvchining tijorat ma'lumotlari maxfiyligini saqlash, malakali texnik yordam ko'rsatish.
        </p>
        <p>
          4.2. <strong>Foydalanuvchi majburiyatlari:</strong> Tanlangan tarif bo'yicha to'lovlarni o'z vaqtida amalga oshirish, Xizmatdan qonunga xilof maqsadlarda foydalanmaslik, intellektual mulk huquqlarini buzmaslik.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900">5. Tariflar va xizmat haqi</h2>
        <p>
          5.1. Xizmatdan foydalanish narxi platforma interfeysining «Tariflar» bo'limida e'lon qilingan amaldagi narxlar bilan belgilanadi.
        </p>
        <p>
          5.2. Ijrochi tariflarni bir tomonlama o'zgartirish huquqiga ega bo'lib, bu haqda kamida 10 kalendar kun oldin platforma orqali yoki elektron pochta orqali xabar beradi.
        </p>
      </section>

      {/* 6-BO'LIM: TO'LOV TARTIBI */}
      <section className="space-y-3 p-5 sm:p-6 bg-slate-50 rounded-2xl border border-slate-200">
        <div className="flex items-center gap-2 text-blue-700 font-bold text-lg">
          <CreditCard className="w-5 h-5" />
          <h2>6. To'lov tartibi va hisob-kitoblar</h2>
        </div>
        <p>
          6.1. <strong>To'lov usullari:</strong> Tariflar va qo'shimcha modullar uchun to'lovlar ulangan to'lov tizimlari hamda internet-ekvayring orqali (jumladan Uzcard, Humo, Visa, Mastercard bank kartalari hamda «UZUM BANK» AJ ekvayring xizmati orqali) naqd pulsiz shaklda amalga oshiriladi.
        </p>
        <p>
          6.2. <strong>Bosqichma-bosqich to'lov jarayoni:</strong> Foydalanuvchi boshqaruv panelida tarifni tanlaydi, «To'lash» tugmasini bosadi, bank ekvayri / protsessing markazining xavfsiz to'lov sahifasiga o'tadi, karta rekvizitlarini kiritadi va bir martalik SMS-kod (OTP) orqali to'lovni tasdiqlaydi.
        </p>
        <p>
          6.3. <strong>Hisob-kitob valyutasi:</strong> O'zbekiston Respublikasi hududida barcha to'lovlar O'zbekiston so'mida (UZS) amalga oshiriladi.
        </p>
        <p>
          6.4. <strong>Fiskal chek:</strong> To'lov muvaffaqiyatli yakunlangach, O'zR soliq qonunchiligi talablariga muvofiq QR-kodli elektron fiskal chek shakllantiriladi va Foydalanuvchiga taqdim etiladi.
        </p>
        <p>
          6.5. <strong>Faollashtirish muddati:</strong> Bank-ekvayrdan muvaffaqiyatli to'lov to'g'risida tasdiq kelishi bilan tarif va tizimga kirish real vaqt rejimida avtomatik ravishda uzaytiriladi.
        </p>
      </section>

      {/* 7-BO'LIM: TO'LOVLAR XAVFSIZLIGI VA ANTIFRAUD (UZUM BANK TALABI BO'YICHA) */}
      <section className="space-y-4 p-5 sm:p-7 bg-amber-50/70 border-2 border-amber-300/80 rounded-2xl">
        <div className="flex items-center gap-2 text-amber-900 font-black text-lg sm:text-xl">
          <Lock className="w-6 h-6 text-amber-700" />
          <h2>7. To'lovlar xavfsizligi va firibgarlik operatsiyalari xavfini cheklash hamda nazorat qilish choralari (Antifraud)</h2>
        </div>

        <div className="space-y-3 text-slate-800">
          <p>
            Ushbu bo'lim Internet-ekvayring shartnomasida (jumladan «UZUM BANK» AJ bilan tuzilgan shartnomada) ko'zda tutilgan cheklovlarni amalga oshirish va Bankning firibgarlikka qarshi kurashish imkoniyatlaridan foydalangan holda firibgarlik operatsiyalari xavfini cheklash va nazorat qilish tartibini belgilaydi:
          </p>

          <ul className="space-y-3 list-none pl-0">
            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">7.1-b.</span>
              <span>
                <strong>Karta ma'lumotlariga aralashmaslik:</strong> Bank kartalari rekvizitlari (karta raqami, amal qilish muddati, CVV/CVC maxfiy kodi) E-Code xizmati axborot tizimlariga aslo kirmaydi va saqlanmaydi. Rekvizitlar Foydalanuvchi tomonidan faqatgina Bank-ekvayrning sertifikatlangan himoyalangan to'lov sahifasida kiritiladi. E-Code xizmati ushbu maxfiy ma'lumotlarni ko'rmaydi, qabul qilmaydi va saqlamaydi.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">7.2-b.</span>
              <span>
                <strong>Xalqaro xavfsizlik standartlari (PCI DSS):</strong> To'lov operatori va Bank-ekvayr xalqaro to'lov tizimlarining eng yuqori PCI DSS xavfsizlik standarti talablari asosida faoliyat yuritadi. Ma'lumotlar uzatishning barcha bosqichlari zamonaviy TLS shifrlash protokollari (kamida 256-bitli kalit) bilan to'liq himoyalangan.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">7.3-b.</span>
              <span>
                <strong>Ikki bosqichli tasdiqlash (3D-Secure / OTP):</strong> Har bir to'lov operatsiyasi karta egasining ishonchli telefon raqamiga karta emitent-banki tomonidan yuboriladigan bir martalik SMS-kod (OTP) orqali majburiy tasdiqlanadi. Bu uchinchi shaxslarning ruxsatsiz to'lov qilish xavfini to'liq bartaraf etadi.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">7.4-b.</span>
              <span>
                <strong>IE shartnomasidagi cheklovlar va bank monitoringi:</strong> Ijrochi Internet-ekvayring shartnomasida ko'zda tutilgan barcha cheklovlarni to'liq qabul qiladi hamda Bankning firibgarlikka qarshi kurashish vositalaridan foydalanadi: bitta operatsiya bo'yicha cheklovlar (limitlar), sutkalik va oylik cheklovlar, shubhali operatsiyalarni to'xtatish yoki bekor qilish choralari Bank va to'lov tizimi darajasida qo'llanadi. Bank tomonidan rad etilgan shubhali operatsiyalar tizimimizda bajarilmaydi — xizmat faqat to'lov to'liq tasdiqlangandan so'ng faollashadi. Shubhali operatsiyani tekshirish yoki bekor qilish bo'yicha Bankning har qanday so'rovi Ijrochi tomonidan so'zsiz bajariladi.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">7.5-b.</span>
              <span>
                <strong>Ichki audit jurnali va monitoring:</strong> E-Code tizimida har bir to'lov buyurtmasi va tranzaksiyasi bo'yicha to'liq elektron audit jurnali (sana, vaqt, summa, holat, tranzaksiya raqami, mijoz hisobi va IP-manzili) yuritiladi. Ushbu jurnal Bank-ekvayr yoki huquqni muhofaza qiluvchi organlarning birinchi so'roviga asosan zudlik bilan taqdim etiladi.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">7.6-b.</span>
              <span>
                <strong>Firibgarlik aniqlanganda hisobni bloklash:</strong> Kompromissga uchragan kartalardan foydalanishga urinish, to'lovlarni ketma-ket muvaffaqiyatsiz kiritish yoki Bankning antifrod-tizimidan ogohlantirish kelganda, qoidabuzar hisob yozuvi darhol xavfsizlik xizmati tomonidan bloklanadi.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">7.7-b.</span>
              <span>
                <strong>Murojaatlarni ko'rib chiqish tezkorligi:</strong> Shubhali to'lovlar yoki ruxsatsiz yechimlar yuzasidan Foydalanuvchilar yoki Bankdan kelgan murojaatlar mutaxassislarimiz tomonidan uzog'i bilan 24 (yigirma to'rt) soat ichida birinchi navbatda ko'rib chiqiladi.
              </span>
            </li>

            <li className="flex items-start gap-3">
              <span className="font-bold text-amber-800 shrink-0">7.8-b.</span>
              <span>
                <strong>Shubhali operatsiyalar bo'yicha maxsus aloqa kanali:</strong> Firibgarlik yoki shubhali to'lovlar yuzasidan tezkor xabar berish uchun maxsus aloqa kanallari faoliyat yuritadi: elektron pochta <code className="bg-white px-2 py-0.5 rounded border border-amber-300 font-mono text-amber-900">antifraud@e-code.uz</code> va ishonch telefoni <code className="bg-white px-2 py-0.5 rounded border border-amber-300 font-mono text-amber-900">+998 88 911 81 71</code>.
              </span>
            </li>
          </ul>
        </div>
      </section>

      {/* 8-BO'LIM: PUL QAYTARISH TARTIBI */}
      <section className="space-y-3 p-5 sm:p-6 bg-slate-50 rounded-2xl border border-slate-200">
        <div className="flex items-center gap-2 text-blue-700 font-bold text-lg">
          <RotateCcw className="w-5 h-5" />
          <h2>8. Pul mablag'larini qaytarish tartibi</h2>
        </div>
        <p>
          8.1. <strong>Qaytarish asoslari:</strong> To'lov xatolik tufayli takroriy yechilganda, tranzaksiya jarayonida texnik uzilish sodir bo'lganda yoki Ijrochining aybi bilan Xizmatdan 48 soatdan ortiq muddat davomida foydalanish imkoni bo'lmaganda to'langan mablag'lar qaytarib berilishi mumkin.
        </p>
        <p>
          8.2. <strong>Murojaat qilish tartibi:</strong> To'lovni qaytarish uchun Foydalanuvchi <code className="font-mono text-blue-700">ecode.uz@gmail.com</code> elektron pochtasiga o'zining F.I.Sh., telefon raqami, to'lov sanasi, summasi va qaytarish sababi ko'rsatilgan rasmiy arizani yuboradi.
        </p>
        <p>
          8.3. <strong>Ko'rib chiqish muddati:</strong> Qaytarish to'g'risidagi ariza Ijrochi tomonidan ariza kelib tushgan kundan boshlab 3 (uch) ish kuni ichida ko'rib chiqiladi va qaror qabul qilinadi.
        </p>
        <p>
          8.4. <strong>Qaytarish muddati va usuli:</strong> Mablag'lar to'lov qaysi bank kartasidan amalga oshirilgan bo'lsa, aynan o'sha kartaga 10 (o'n) bank ish kuni ichida to'liq qaytariladi (aniq muddat karta emitent-bankining ish tartibiga bog'liq).
        </p>
        <p>
          8.5. <strong>Komissiya olinmasligi:</strong> Mablag'larni qaytarishda Foydalanuvchidan hech qanday qo'shimcha komissiya yoki jarima ushlab qolinmaydi.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900">9. Nizolarni hal qilish tartibi</h2>
        <p>
          9.1. Ushbu Oferta saytda e'lon qilingan paytdan boshlab kuchga kiradi va noma'lum muddatga amal qiladi.
        </p>
        <p>
          9.2. Shartnoma yuzasidan kelib chiqadigan barcha kelishmovchiliklar muzokaralar orqali hal qilinadi. Kelishuvga erishilmagan taqdirda, nizo O'zbekiston Respublikasi amaldagi qonunchiligiga muvofiq sud tartibida ko'rib chiqiladi.
        </p>
      </section>
    </div>
  );
}
