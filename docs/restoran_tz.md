# E-Code Restoran: Texnik topshiriq (TZ)

Versiya 1.0, 2026-11-26. Holat: kelishish uchun.

## 0. Qisqacha

Ro'yxatdan o'tishda korxona o'z **biznes turini** tanlaydi: **Savdo (do'kon)** yoki **Restoran / kafe**.
Restoran tanlansa, korxona alohida tizimga emas, o'sha E-Code ERP'ga tushadi, lekin unga restoran
rejimi yoqiladi: boshqa menyu, boshqa kassa ekrani, ofitsiant va oshxona ekranlari, texnologik kartalar,
zal va stollar. Ombor, xarid, ta'minotchilar, moliya, smena, fiskal, xodimlar, Telegram bot, kuryerlar
umumiy yadrodan foydalanadi.

Bu yo'l dorixona modulida sinalgan: `companies.pharmacy_enabled` bayrog'i o'chiq bo'lsa dorixona
qoidalari ishlamaydi. Restoran ham xuddi shunday, alohida bayroq va alohida jadvallar bilan quriladi.
Oddiy do'konlarga hech narsa o'zgarmaydi.

**Asosiy tamoyillar**

1. Bitta kod bazasi, bitta ma'lumotlar bazasi. Alohida "restoran ERP" fork qilinmaydi.
2. Restoran jadvallari faqat restoran korxonasida to'ladi; do'konda ular bo'sh turadi.
3. Har bir to'langan chek mavjud `Sale` sifatida yoziladi. Shunda kassa, fiskal, moliya, P&L, hisobotlar
   qayta yozilmasdan ishlaydi.
4. Taom sotilganda omborda taom emas, uning **ingredientlari** texnologik karta bo'yicha kamayadi.
5. Oshxonaga yuborilgan narsani o'chirish faqat sabab bilan va ruxsat bilan. Har bir harakat audit logga.

---

## 1. Ro'yxatdan o'tish

### R0.1 Biznes turini tanlash

`RegisterCompany.jsx` da 1-qadam ("Korxona") boshiga tanlov qo'shiladi, mavjud maydonlar o'zgarmaydi:

| Karta | Qiymat | Izoh |
|---|---|---|
| Savdo / do'kon | `retail` | Hozirgi ERP, sukut |
| Restoran / kafe | `restaurant` | Restoran rejimi |

Restoran tanlansa, qo'shimcha bitta savol: **format**.

| Format | Qiymat | Nima o'zgaradi |
|---|---|---|
| Restoran (stol xizmati) | `full_service` | Zal, stol, ofitsiant, xizmat haqi yoqilgan |
| Kafe / kofeyna | `cafe` | Stollar bor, xizmat haqi sukut 0% |
| Fast-food / olib ketish | `fast_food` | Stol yo'q, kassada buyurtma, buyurtma raqami ekrani |
| Oshxona / choyxona | `canteen` | Stol ixtiyoriy, tez kassa |

Format faqat boshlang'ich sozlamalarni belgilaydi, keyin Sozlamalarda o'zgartirsa bo'ladi.

Login sahifasidagi "Ro'yxatdan o'ting" havolasi va landingdagi tugmalar `?type=restaurant` parametrini
qabul qiladi, shunda restoran reklamasidan kelgan odamga karta oldindan tanlangan holda ochiladi.

Dorixona ro'yxatdan o'tishda ko'rsatilmaydi: hozirgidek pullik paket bo'lib qoladi, Super Admin yoqadi (kelishilgan).

### R0.2 Backend

- `CompanyRegisterRequest` ga `business_type: Literal['retail','restaurant'] = 'retail'` va
  `restaurant_format: Optional[str]` qo'shiladi.
- `companies` jadvaliga:
  - `business_type String(20) NOT NULL DEFAULT 'retail'`, CHECK `('retail','restaurant')`
  - `restaurant_settings JSON NULL` (11-bo'lim)
- Mavjud korxonalar migratsiyada `retail` bo'ladi.

### R0.3 Restoran korxonasi yaratilganda avtomatik tayyorlanadigan narsalar

Mavjud `register` mantiqi (filial, asosiy ombor, kassa, admin) o'zgarmaydi. Ustiga:

- Omborlar: "Asosiy ombor" (xom ashyo) va "Oshxona" (ishlab chiqarish ombori).
- Sexlar (stansiyalar): "Issiq sex", "Sovuq sex", "Bar".
- Zal: "Asosiy zal", 10 ta stol (fast-food formatida yaratilmaydi).
- Kategoriyalar: Salatlar, Birinchi taomlar, Ikkinchi taomlar, Gril, Ichimliklar, Desertlar, Non.
- Rollar: Menejer, Administrator, Ofitsiant, Oshpaz, Barmen, Kassir, Omborchi, Kuryer
  (R3/R6 da, restoran ruxsat kalitlari paydo bo'lganda yaratiladi).
- Sozlamalar formatga mos sukut qiymatlar bilan.

### R0.4 Menyu (sidebar) ajratish

`business_type = 'restaurant'` bo'lsa admin panelda:

- **Ko'rinadi:** Bosh sahifa, Zal va stollar, Buyurtmalar, Kassa (restoran), Oshxona ekrani, Menyu,
  Texnologik kartalar, Ombor, Xaridlar, Ta'minotchilar, Inventarizatsiya, Chiqim (spisanie), Bron,
  Yetkazish, Mijozlar, Xodimlar, Smenalar, Moliya, Hisobotlar, Sozlamalar.
- **Yashiriladi:** Ulgurji sotuv, Distribyutorlar, Agentlar (SFA), Marketplace agentlar, Dorixona,
  narx teglari va shtrix-kod chop etish.

Backend ham himoyalanadi: restoran endpointlari `require_restaurant` dependency orqali, do'kon korxonasi
chaqirsa 403. Xuddi shu yo'l dorixona endpointlarida ishlatilgan.

### R0.5 Mavjud korxonani o'tkazish

Super Admin panelida korxonaning biznes turini o'zgartirish. Restorandan do'konga qaytarishda restoran
ma'lumotlari o'chirilmaydi, faqat yashiriladi.

---

## 2. Menyu va texnologik kartalar

### R1.1 Mahsulot turlari

`products` jadvaliga `item_kind String(20) NOT NULL DEFAULT 'goods'`:

| Qiymat | Ma'nosi | Sotiladimi | Omborda turadimi |
|---|---|---|---|
| `goods` | Tayyor tovar (Coca-Cola, suv) | Ha | Ha |
| `dish` | Taom (texnologik karta bilan) | Ha | Yo'q, ingredientlari kamayadi |
| `semi` | Yarim tayyor mahsulot (qiyma, bulon, sous) | Yo'q (sukut) | Ha |
| `ingredient` | Xom ashyo (go'sht, un, yog') | Yo'q | Ha |
| `modifier` | Qo'shimcha (pishloq, sous) | Faqat taomga qo'shib | Ixtiyoriy |

- Taom uchun shtrix-kod majburiy emas: `barcode` NOT NULL bo'lgani uchun avtomatik ichki kod beriladi.
- Ingredient birliklari: kg, l, dona. Miqdorlar `Numeric(12,3)` (1 g aniqlik). `min_stock` hozir Integer,
  restoran uchun `Numeric(12,3)` ga o'tkaziladi.
- Shtrix-kod limiti (tarif) restoranda taomlarni sanamaydi.

### R1.2 Texnologik karta (tex karta)

Mavjud `boms` / `bom_items` kengaytiriladi (yangi jadval ochilmaydi):

- `boms`: `output_qty` (karta beradigan chiqish, mahsulot birligida: taom uchun 1 porsiya, yarim tayyor uchun
  masalan 5 kg), `output_weight_g` (porsiya og'irligi, ma'lumot uchun), `cooking_time_min`, `instructions`,
  `version`, `created_by`. Rasm mahsulotning o'z rasmidan olinadi.
- `bom_items`: `gross_qty` (brutto, butun karta uchun), `net_qty` (netto), `loss_cold_pct`, `loss_hot_pct`.
  Birlik ingredient mahsulotining birligi. `quantity_per_unit = gross_qty / output_qty` (1 birlik uchun), shu
  qiymatni ishlab chiqarish va R7.1 yechish ishlatadi. Ombordan **brutto** kamayadi; tannarx brutto bo'yicha.
- Ingredient sifatida `semi` ham bo'lishi mumkin (ichma-ich karta). Aylana bog'lanish taqiqlanadi.
- Tex karta o'zgarsa yangi versiya yaratiladi, eski sotuvlar eski versiya bo'yicha qoladi.
- Ekranda: har bir qatorning narxi, taomning to'liq tannarxi, **food cost %** = tannarx / sotuv narxi.
  Food cost belgilangan chegaradan (sukut 35%) oshsa qizil.
- Excel import/eksport (mavjud mahsulot importi kabi): 2-bosqichga ko'chirildi.

### R1.3 Modifikatorlar

- `modifier_groups`: nomi, `min_select`, `max_select`, majburiymi (masalan "Pishirish darajasi", 1 ta majburiy).
- `modifiers`: guruh, nomi, qo'shimcha narx, ixtiyoriy bog'langan mahsulot va miqdor
  (ombordan kamayishi uchun).
- `product_modifier_groups`: qaysi taomga qaysi guruh.

### R1.4 Sexlar (stansiyalar) va yo'naltirish

- `kitchen_stations`: korxona darajasida (nomi, KDS yoqilganmi, tartib). Taom yoki kategoriya bitta sexga
  biriktiriladi va hamma filialda shu sexga ketadi.
- Filial bo'yicha printer manzili (pos-desktop orqali ESC/POS) R4.1 da alohida jadvalda: `station_printers`
  (sex, filial, printer).
- Kategoriya yoki taomga sex biriktiriladi (taomdagi qiymat ustun).
- Buyurtma yuborilganda har bir sexga faqat o'zining qatorlari ketadi.

### R1.5 Stop-list

- Taomni filial bo'yicha vaqtincha sotuvdan olish (sabab, kim, qachongacha).
- Ixtiyoriy: "qoldi N porsiya" hisoblagichi, nolga tushsa avtomatik stop.
- Ingredient tugasa (qoldiq tex karta uchun yetmasa) ogohlantirish, sozlama bo'yicha avtomatik stop.
- Stop-list ofitsiant, kassa, Telegram menyuda bir zumda ko'rinadi.

### R1.6 Narxlar

- Filial bo'yicha narx: mavjud `branch_prices` ishlatiladi.
- Vaqtga bog'liq narx va menyu (nonushta 08:00-11:00, happy hour) 3-bosqichda.

---

## 3. Zal va stollar

### R2.1 Ma'lumotlar

- `halls`: filial, nomi, tartib, xizmat haqi foizi (VIP zal uchun alohida bo'lishi mumkin).
- `restaurant_tables`: zal, raqami/nomi, o'rinlar soni, sxemadagi joyi (`x, y, w, h, shape`), faolmi.

### R2.2 Zal sxemasi

- Admin rejimida stollarni sudrab joylash (to'rtburchak/dumaloq), saqlash.
- Ishchi rejimida stol rangi holatga qarab:

| Holat | Rang | Qachon |
|---|---|---|
| Bo'sh | Kulrang | Ochiq chek yo'q |
| Band | Ko'k | Ochiq chek bor |
| Hisob so'ralgan | Sariq | Pre-chek chop etilgan |
| Bron | Binafsha | Yaqin 60 daqiqada bron bor |
| Kechikkan | Qizil | Taom tayyor, lekin 5 daqiqadan ko'p berilmagan |

- Stolda: ofitsiant ismi, mehmonlar soni, chek summasi, ochilganiga necha daqiqa.

### R2.3 Stol amallari

- Chekni boshqa stolga ko'chirish.
- Ikki stolni birlashtirish.
- Chekni boshqa ofitsiantga o'tkazish (ruxsat bilan).
- Bitta stolda bir nechta chek (alohida kompaniyalar).

---

## 4. Buyurtma (chek) jarayoni

### R3.1 Ma'lumotlar

`restaurant_orders` (restoran cheki, mavjud `orders` jadvali bilan aralashtirilmaydi):

| Maydon | Izoh |
|---|---|
| `number` | Filial va kun bo'yicha ketma-ket (mavjud `document_counter`) |
| `company_id`, `branch_id`, `shift_id` | |
| `order_type` | `dine_in`, `takeaway`, `delivery` |
| `table_id`, `guests` | Zalda bo'lsa |
| `waiter_id` | Ochgan / mas'ul xodim |
| `customer_id` | Ixtiyoriy (sodiqlik, yetkazish) |
| `status` | `open`, `prechecked`, `paid`, `cancelled` |
| `subtotal`, `discount_amount`, `service_pct`, `service_amount`, `total` | |
| `sale_id` | To'langanda yaratilgan `Sale` |
| `opened_at`, `prechecked_at`, `closed_at`, `comment` | |

`restaurant_order_items`:

| Maydon | Izoh |
|---|---|
| `order_id`, `product_id`, `bom_id` (versiya) | |
| `quantity Numeric(12,3)`, `unit_price`, `modifiers JSON`, `modifiers_total` | |
| `course` | 1, 2, 3 (navbat bilan chiqarish) |
| `guest_no` | Hisobni bo'lish uchun |
| `station_id` | |
| `status` | `draft`, `sent`, `cooking`, `ready`, `served`, `cancelled` |
| `sent_at`, `cooking_at`, `ready_at`, `served_at` | |
| `cancel_reason`, `cancelled_by`, `cancel_approved_by`, `write_off` | |
| `comment` | "Piyozsiz" va h.k. |

### R3.2 Oqim

1. Ofitsiant stolni tanlaydi, mehmonlar sonini kiritadi, chek ochiladi.
2. Taomlarni qo'shadi (kategoriya, qidiruv, sevimlilar), modifikator va izoh qo'shadi, kurs belgilaydi.
3. **"Oshxonaga yuborish"**: `draft` qatorlar `sent` bo'ladi, har bir sexga tiket chop etiladi / KDS'ga chiqadi.
   Kurs bo'yicha "ushlab turish" va keyin "2-kursni chiqarish" tugmasi.
4. Oshxona tayyorlaydi (5-bo'lim), ofitsiantga "tayyor" xabari keladi.
5. Mehmon hisob so'raydi: **pre-chek** chop etiladi, chek `prechecked` bo'ladi va tahrirdan qulflanadi.
   Qulfni ochish faqat menejer ruxsati bilan.
6. Kassada to'lov (6-bo'lim), chek `paid`, stol bo'shaydi.

### R3.3 O'chirish va bekor qilish (firibgarlikka qarshi)

- `draft` qatorni ofitsiant erkin o'chiradi.
- `sent` va undan keyingi qatorni o'chirish: sabab tanlash majburiy ("Mehmon voz kechdi", "Xato kiritildi",
  "Taom buzildi", "Uzoq kutildi") + menejer PIN.
- Taom tayyorlangan bo'lsa (`cooking` yoki `ready`) ingredientlar **chiqimga** (spisanie) yoziladi,
  aks holda omborga ta'sir qilmaydi.
- Har bir bekor qilish, chegirma, pre-chekdan keyin tahrir, stol ko'chirish `audit_logs` ga yoziladi va
  "Bekor qilishlar" hisobotida chiqadi.

### R3.4 Chegirma va xizmat haqi

- Chegirma: foiz yoki summa, butun chekka yoki qatorga. Rol bo'yicha maksimal foiz (masalan ofitsiant 0%,
  administrator 10%, menejer 100%).
- Xizmat haqi (obslujivaniye): zal yoki filial sozlamasi, olib ketish va yetkazishda 0.
  Xizmat haqi chegirmadan keyingi summadan hisoblanadi (sozlama).
- Choy puli (tips): to'lovda alohida kiritiladi, ofitsiant hisobiga yoziladi, sotuv tushumiga qo'shilmaydi.

---

## 5. Oshxona

### R4.1 Oshxona printeri

- Har bir sex uchun tiket: chek raqami, stol, ofitsiant, vaqt, taomlar, modifikatorlar, izoh, kurs.
- Bekor qilingan qator uchun "BEKOR" tiketi.
- Chop etish pos-desktop (Electron) orqali; printer topilmasa kassada ogohlantirish va qayta chop etish.

### R4.2 KDS (oshxona ekrani)

- Brauzerda ishlaydigan sahifa (planshet / televizor), sex bo'yicha filtr.
- Kartochkalar: chek, stol, vaqt taymeri, taomlar. Tayyorlash normasi (`cooking_time_min`) oshsa
  kartochka sariq, ikki baravar oshsa qizil.
- Bosish: `sent` -> `cooking` -> `ready`. "Tayyor" bo'lganda ofitsiant ekraniga va mobil ilovasiga xabar.
- Bir xil taomlarni yig'ib ko'rsatish rejimi ("hozir jami 6 ta osh").
- Yangilanish real vaqtda (WebSocket); ulanish uzilsa avtomatik qayta ulanish va so'nggi holatni tortish.

---

## 6. Kassa (restoran rejimi)

### R5.0 Ikki xil kassa (kelishilgan)

| Kassa | Internet | Izoh |
|---|---|---|
| Web kassa (admin panel ichida) | Faqat onlayn | Oflayn rejim yo'q |
| **E-Code POS Restoran** (Windows ilova) | Oflayn ishlaydi | Dorixona build'i kabi alohida build va yangilanish kanali |

Restoran desktop ilovasi dorixona uchun qilingan E-Code POS asosida quriladi: oflayn navbat, lokal kesh,
printerlar, avtoyangilanish. Internet uzilganda ham chek ochish, oshxonaga chop etish va to'lov qabul qilish
ishlaydi; internet qaytganda hammasi serverga yuboriladi.

### R5.1 Ekran

- Restoran korxonasida kassa boshqa ko'rinishda ochiladi:
  chap tomonda zal sxemasi yoki ochiq cheklar ro'yxati, o'ng tomonda tanlangan chek.
- Fast-food formatida: zal yo'q, darhol menyu va savat, to'lovdan keyin buyurtma raqami beriladi.

### R5.2 To'lov

- Usullar: naqd, karta (terminal), Click, Payme, Uzum, aralash to'lov. Mavjud to'lov turlari va
  `payment_terminals` ishlatiladi.
- Qaytim hisoblash.
- **Hisobni bo'lish:** teng bo'lish (N kishiga), mehmon bo'yicha (`guest_no`), qatorlarni tanlab.
  Har bir qism alohida to'lov va alohida fiskal chek.
- To'lov tugagach:
  1. `Sale` yaratiladi (mavjud `sale_create` servisi orqali). Qatorlar taom sifatida, xizmat haqi alohida
     xizmat qatori sifatida.
  2. Fiskal chek (mavjud `fiscal` moduli). Taomlar uchun MXIK kodi va QQS mahsulot kartasidan.
  3. Ingredientlar ombordan yechiladi (8-bo'lim).
  4. Kassa va smena hisobiga yoziladi (mavjud mantiq).
- Qaytarish: to'langan chekni qaytarish mavjud qaytarish jarayoni orqali, menejer ruxsati bilan.

### R5.3 Smena

Mavjud smenalar. Restoranda smena yopilmasdan oldin ochiq cheklar bo'lsa ogohlantirish, ro'yxat ko'rsatiladi.
Smena hisobotida: tushum to'lov turlari bo'yicha, xizmat haqi, choy puli, bekor qilishlar, chegirmalar.

---

## 7. Ofitsiant ilovasi

### R6.1 Planshet / telefon (web, PWA)

- Xodim telefoni + PIN (4 raqam) bilan tez kirish; bitta planshetda bir nechta ofitsiant almashib ishlaydi.
- Ekranlar: Zal, Mening stollarim, Chek, Menyu, Bildirishnomalar ("tayyor", "stol chaqiryapti").
- Ofitsiant faqat o'z stollarini tahrirlaydi (sozlama: hamma stol).
- To'lovni ofitsiant qabul qilishi mumkinmi: sozlama (sukut: yo'q, faqat kassa).

### R6.2 Mobil ilova

Mavjud Flutter ilovasiga (`mobile/`) "Ofitsiant" rejimi 2-bosqichda. 1-bosqichda PWA yetarli.

### R6.3 Oflayn

Ofitsiant PWA va web kassa faqat onlayn ishlaydi. Oflayn rejim faqat E-Code POS Restoran
desktop ilovasida (R5.0). Internet uzilsa ofitsiantlar buyurtmani kassadagi desktop ilovaga kiritadi.

---

## 8. Ombor (restoran)

### R7.1 Avtomatik yechish

- Taom sotilganda tex karta bo'yicha brutto miqdorlar "Oshxona" omboridan yechiladi
  (sozlama: qaysi ombordan).
- `semi` ingredientlar: agar oldindan tayyorlangan bo'lsa (qoldig'i bor) o'zidan, aks holda uning tex kartasi
  bo'yicha xom ashyogacha yoyiladi (sozlama).
- Modifikator bog'langan mahsulot ham yechiladi.
- Yechish vaqti: sozlama, `paid` (sukut) yoki `sent` (oshxonaga yuborilganda).
- Qoldiq minusga tushsa: sotuv to'xtamaydi, "Manfiy qoldiqlar" ogohlantirishi va hisobot.

### R7.2 Yarim tayyor mahsulot ishlab chiqarish

Mavjud ishlab chiqarish buyurtmalari (`production_orders`) ishlatiladi: "10 kg qiyma tayyorlash"
xom ashyoni kamaytiradi, `semi` qoldig'ini oshiradi. Restoranda soddalashtirilgan forma.

### R7.3 Chiqim (spisanie)

- Sabablar: buzilgan, muddati o'tgan, xodim ovqati, mehmonga sovg'a (komplement), bekor qilingan taom, boshqa.
- Taom bo'yicha chiqim (tex karta bilan yoyiladi) yoki ingredient bo'yicha.
- Har bir chiqim tannarx bilan, hisobotda sabab bo'yicha.

### R7.4 Ko'chirish va inventarizatsiya

- Asosiy ombor -> Oshxona ko'chirish (mavjud `transfers`).
- Inventarizatsiya ingredientlar bo'yicha (mavjud `inventory_counts`), natijada **nazariy va haqiqiy sarf**
  farqi: tex karta bo'yicha qancha ketishi kerak edi, aslida qancha ketdi.

### R7.5 Xarid

Mavjud xaridlar va ta'minotchilar. Qo'shimcha: kirimda ingredient narxi o'zgarsa tex kartalar tannarxi
qayta hisoblanadi, food cost chegarasidan oshgan taomlar ro'yxati chiqadi.

---

## 9. Bron, yetkazish, mijozlar

### R8.1 Bron

- `reservations`: filial, stol(lar), sana-vaqt, davomiylik, mehmonlar soni, mijoz, telefon, oldindan to'lov
  (depozit), izoh, holat (`booked`, `arrived`, `no_show`, `cancelled`).
- Kalendar va zal sxemasida ko'rinadi. Bir stolga vaqt kesishsa rad.
- Depozit chekni yopishda avtomatik hisobga olinadi.
- Eslatma: Telegram yoki SMS (mavjud `sms`, `telegram`), bron vaqtidan 2 soat oldin.

### R8.2 Yetkazish va olib ketish

- Telegram Mini App (mavjud `shop`) restoran menyusini ko'rsatadi: modifikatorlar, stop-list, rasm.
- Bot buyurtmasi `restaurant_orders` ga `order_type = delivery/takeaway` bilan tushadi va oshxonaga yuboriladi
  (sozlama: avtomatik yoki operator tasdiqlagandan keyin).
- Kuryerlar: mavjud kuryer moduli va kuryer boti.
- Yetkazish zonalari (radius yoki poligon) va har bir zona narxi.
- Agregatorlar (Uzum Tezkor, Yandex Eats, Express24): 3-bosqich, API kirish olinishiga bog'liq.

### R8.3 QR menyu

Stol ustidagi QR: mehmon menyuni ko'radi (1-qism), keyin o'zi buyurtma beradi va ofitsiantni chaqiradi
(3-bosqich).

### R8.4 Mijozlar va sodiqlik

Mavjud mijozlar va `loyalty` (keshbek, bonus). Qo'shimcha: tug'ilgan kun chegirmasi, tashriflar soni,
o'rtacha chek.

---

## 10. Xodimlar va ruxsatlar

| Rol | Asosiy huquqlar |
|---|---|
| Egasi | Hammasi |
| Menejer | Hammasi, sozlamalardan tashqari; bekor qilish va chegirmani tasdiqlash |
| Administrator (zal) | Zal, bron, chekni ko'chirish, chegirma limit bilan |
| Ofitsiant | O'z cheklari, oshxonaga yuborish, pre-chek |
| Kassir | To'lov, smena, qaytarish (ruxsat bilan) |
| Oshpaz / Barmen | KDS, stop-list, tex kartani ko'rish |
| Omborchi | Kirim, ko'chirish, inventarizatsiya, chiqim |
| Kuryer | Kuryer boti |

- Mavjud `roles` modeli kengaytiriladi; yangi huquq kalitlari: `rest.order.cancel_sent`,
  `rest.order.discount`, `rest.order.unlock_precheck`, `rest.table.move`, `rest.kds`, `rest.stoplist`.
- PIN kod xodim profilida. Menejer PIN'i boshqa xodim ekranida tasdiq uchun.
- Ofitsiant ish haqi: xizmat haqining foizi yoki sotuvdan foiz (mavjud `employee_commission`).

---

## 11. Sozlamalar (`restaurant_settings`)

| Kalit | Sukut | Izoh |
|---|---|---|
| `format` | ro'yxatdan | `full_service`, `cafe`, `fast_food`, `canteen` |
| `service_pct` | 10 (`full_service`), qolganda 0 | Xizmat haqi |
| `service_after_discount` | true | |
| `deduct_stock_on` | `paid` | yoki `sent` |
| `semi_auto_expand` | true | |
| `precheck_lock` | true | |
| `waiter_can_take_payment` | false | |
| `waiter_sees_all_tables` | false | |
| `food_cost_alert_pct` | 35 | |
| `auto_stop_on_no_stock` | false | |
| `delivery_auto_send_kitchen` | false | |
| `order_number_screen` | `fast_food` da true | |

Sozlamalar sahifasida alohida "Restoran" bo'limi, faqat restoran korxonasida ko'rinadi.

---

## 12. Hisobotlar

1. **Kunlik hisobot (Z):** tushum, to'lov turlari, cheklar soni, o'rtacha chek, mehmonlar soni,
   o'rtacha chek bir mehmonga, xizmat haqi, choy puli, chegirmalar, bekor qilishlar.
2. **Taomlar bo'yicha sotuv:** soni, tushum, tannarx, foyda, food cost %.
3. **Menyu muhandisligi (ABC):** har bir taom sotuv soni va foydaga qarab 4 guruhga:
   yulduz (ko'p sotiladi, foydali), ishchi ot (ko'p sotiladi, kam foyda), jumboq (kam sotiladi, foydali),
   it (kam sotiladi, kam foyda). Har guruhga tavsiya.
4. **Ofitsiantlar:** cheklar, tushum, o'rtacha chek, bekor qilishlar, chegirmalar, choy puli.
5. **Soatlar va kunlar bo'yicha yuklama** (issiqlik xaritasi).
6. **Stol aylanishi:** stol bir kunda necha marta band bo'ldi, o'rtacha o'tirish vaqti.
7. **Oshxona tezligi:** yuborishdan tayyorgacha o'rtacha vaqt, sex va taom bo'yicha.
8. **Bekor qilishlar va chegirmalar (anti-fraud):** kim, qachon, nima, sabab, kim tasdiqladi.
9. **Ombor:** ingredient qoldig'i, nazariy va haqiqiy sarf, chiqimlar sabab bo'yicha, manfiy qoldiqlar.
10. **P&L:** mavjud moliya hisoboti; tannarx tex karta bo'yicha.

Bosh sahifa (restoran): bugungi tushum, ochiq stollar, ochiq cheklar summasi, oshxonadagi navbat,
kechikayotgan taomlar, bugungi bronlar, stop-listdagi taomlar.

---

## 13. Texnik talablar

- **Real vaqt:** zal holati, KDS, ofitsiant bildirishnomalari WebSocket orqali (FastAPI), filial bo'yicha kanal.
  Kanal faqat o'z korxonasi ma'lumotini oladi.
- **Tezlik:** "Oshxonaga yuborish" bosilgandan KDS'da paydo bo'lishigacha 1 soniyadan kam;
  zal sxemasi 100 stolgacha 1 soniyada yuklanadi.
- **Bir vaqtda tahrir:** bitta chekni ikki qurilma tahrirlasa `version` maydoni bilan optimistik qulf,
  ikkinchisiga "chek yangilandi" xabari.
- **Izolyatsiya:** barcha yangi jadvallarda `company_id` va indeks; RLS siyosati mavjud reja bo'yicha.
- **Audit:** 3.3 dagi barcha amallar `audit_logs` ga.
- **Migratsiyalar:** Alembic, oldinga va orqaga; mavjud korxonalar ma'lumotiga tegmaydi.
- **Testlar:** har bir vazifa uchun pytest (`tests/restaurant/test_R*.py`), mavjud `tests/branch_audit`
  uslubida. Asosiy holatlar: tex karta bo'yicha yechish, bekor qilish va chiqim, hisobni bo'lish va fiskal,
  do'kon korxonasida restoran endpointlari 403.
- **Uskunalar:** ESC/POS printerlar (58/80 mm) pos-desktop orqali, LAN printer IP bo'yicha;
  KDS uchun istalgan planshet yoki brauzerli televizor.
- **UI:** mavjud uslub, ixcham va tekis; gradient, porlash, emoji yo'q.

---

## 14. Bosqichlar

### 1-bosqich: Asos (MVP)

Maqsad: kichik kafe yoki restoran E-Code'da to'liq bir kun ishlay olsin.

| Kod | Vazifa |
|---|---|
| R0.1-R0.5 | Biznes turi, ro'yxatdan o'tish, avtomatik tayyorlash, menyu ajratish |
| R1.1, R1.2, R1.4 | Mahsulot turlari, tex karta, sexlar |
| R2.1-R2.3 | Zal, stollar, sxema |
| R3.1-R3.4 | Chek, oshxonaga yuborish, pre-chek, bekor qilish, chegirma, xizmat haqi |
| R4.1 | Oshxona printeri |
| R5.0-R5.3 | Web kassa (onlayn), E-Code POS Restoran desktop (oflayn), to'lov, `Sale` va fiskal, smena |
| R9.1 | Super Admin: Restoranlar bo'limi va restoran tariflari |
| R6.1 | Ofitsiant PWA |
| R7.1, R7.3, R7.4 | Avtomatik yechish, chiqim, ko'chirish, inventarizatsiya |
| Hisobot 1, 2, 4, 8 | Kunlik, taomlar, ofitsiantlar, bekor qilishlar |

**Qabul mezoni:** yangi restoran ro'yxatdan o'tadi; 20 ta taom va tex karta kiritadi; ingredient kirim qiladi;
ofitsiant stol ochib buyurtma yuboradi, oshxonada tiket chiqadi; kassada aralash to'lov bilan yopiladi,
fiskal chek chiqadi; ingredientlar tex karta bo'yicha kamaygan; kunlik hisobot to'g'ri.
Do'kon korxonasida hech narsa o'zgarmagan (mavjud testlar o'tadi).

### 2-bosqich: Professional

| Kod | Vazifa |
|---|---|
| R1.3 | Modifikatorlar |
| R1.5 | Stop-list |
| R4.2 | KDS ekrani, real vaqt |
| R5.2 | Hisobni bo'lish |
| R6.2 | Flutter ilovada ofitsiant rejimi |
| R7.2, R7.5 | Yarim tayyor ishlab chiqarish, tannarx qayta hisobi |
| R8.1 | Bron |
| Hisobot 3, 5, 6, 7, 9 | ABC, yuklama, stol aylanishi, oshxona tezligi, ombor |

### 3-bosqich: O'sish

| Kod | Vazifa |
|---|---|
| R8.2 | Telegram yetkazish restoran menyusi bilan, zonalar, agregatorlar |
| R8.3 | QR menyu va QR buyurtma |
| R8.4 | Sodiqlik kengaytmasi |
| R1.6 | Vaqtga bog'liq menyu va narx |
| | Fast-food buyurtma raqami ekrani, o'zi buyurtma berish kiosk |

---

## 15. Super Admin: Restoranlar bo'limi va tariflar (R9.1, kelishilgan)

Super Admin panelida alohida **"Restoranlar"** bo'limi:

- Restoran korxonalari ro'yxati: format, filiallar, obuna holati, oxirgi faollik, bugungi cheklar soni.
- Restoran tariflari alohida: `tariffs` jadvaliga `business_type` ustuni qo'shiladi, do'kon tariflari va
  restoran tariflari bir-biriga aralashmaydi. Restoran korxonasi faqat restoran tariflarini ko'radi va sotib oladi.
- Har bir tarif Super Admin'da sozlanadi: nomi, narxi (BHM ulushi), filial, xodim, ofitsiant qurilmalari,
  KDS ekranlari soni, qaysi imkoniyatlar kiradi (KDS, bron, yetkazish, agregatorlar, QR menyu).
- Restoran uchun ro'yxatdan o'tishda beriladigan sinov tarifi alohida belgilanadi.
- Yetkazish va agregatorlar pullik paket sifatida ham sotilishi mumkin (mavjud `feature_packages`).

Boshlang'ich taklif (Super Admin'da o'zgartiriladi):

| Tarif | BHM ulushi | Filial | Xodim |
|---|---|---|---|
| Kafe | 40% | 1 | 8 |
| Restoran | 70% | 1 | 25 |
| Tarmoq | 95% + filial uchun qo'shimcha | cheksiz | cheksiz |

---

## 16. Ochiq savollar (qaror kerak)

Kelishilgan (2026-11-26):

- Dorixona hozirgidek pullik paket bo'lib qoladi, ro'yxatdan o'tishda chiqmaydi.
- Web faqat onlayn. Oflayn rejim E-Code POS Restoran desktop ilovasida (R5.0).
- Sinov uchun real restoran bor.
- Restoran tariflari Super Admin'dagi alohida "Restoranlar" bo'limida sozlanadi (15-bo'lim).
- Xizmat haqi sukut: stolli restoran 10%, kafe, fast-food va oshxonada 0%. Har bir restoran o'zgartira oladi.
- Ingredient sukut bo'yicha chek to'langanda yechiladi (`deduct_stock_on = paid`); sozlamada `sent` ga o'tkaziladi.

Hali ochiq:

1. Restoran qaysi yetkazish ilovalarida ishlaydi (Yandex Eats, Uzum Tezkor, Express24). 3-bosqichgacha kerak emas.
2. Sinov restorani formati: stolli restoran, kafe yoki fast-food; nechta stol va filial.

## 17. Bajarilish holati

| Vazifa | Holat |
|---|---|
| R0.1 Ro'yxatdan o'tishda biznes turi va format, `/register?type=restaurant` | Bajarildi |
| R0.2 `companies.business_type`, `restaurant_settings`, `tariffs.business_type` (migratsiya `r0_1`) | Bajarildi |
| R0.3 Oshxona ombori, sexlar, zal va 10 stol, kategoriyalar, sozlamalar (yangi filialda ham) | Bajarildi. Rollar R3/R6 da, ruxsat kalitlari bilan birga |
| R0.4 Menyu ajratish, `require_restaurant`, `/restaurant/settings`, `/restaurant/layout` | Bajarildi |
| R0.5 Super Admin'da biznes turi va formatni almashtirish (audit bilan) | Bajarildi |
| R1.1 `products.item_kind`, taom o'z qoldig'isiz (`product_type = service`), ichki kod | Bajarildi (`min_stock` ni kasr songa o'tkazish R7 da) |
| R1.2 Tex karta: brutto/netto/yo'qotish, chiqish, versiyalar, ichma-ich tannarx, food cost, valyuta | Bajarildi (Excel import 2-bosqichda) |
| R1.4 Sexlar (korxona darajasida), kategoriya va taom bo'yicha sex | Bajarildi |
| Menyu sahifasi `/admin/restaurant/menu` (taomlar, yarim tayyor, ingredientlar, tovarlar, sexlar) | Bajarildi |
| R2.1 Zallar va stollar: qo'shish, tahrirlash, nofaol qilish, zal bo'yicha xizmat haqi, filial doirasi | Bajarildi |
| R2.2 Zal sxemasi `/admin/restaurant/floor`: sudrab joylash, o'lcham, shakl, bir yo'la saqlash (audit) | Bajarildi. Stol holatlari ranglari R3 da (ochiq cheklarga bog'liq) |
| R2.3 Stolni ko'chirish, birlashtirish, bir stolda bir nechta chek, chekni boshqa xodimga o'tkazish | Bajarildi (R3 bilan) |
| R2.2 Stol holatlari: bo'sh, band, taom tayyor, hisob so'ralgan (15 soniyada yangilanadi) | Bajarildi. Bron holati R8.1 da |
| R3.1-R3.2 Chek, qatorlar (narx va tex karta versiyasi surati), kurslar, oshxonaga yuborish (sex tiketlari), pre-chek va qulf | Bajarildi |
| R3.3 Bekor qilish: sabab, menejer PIN tasdig'i (5 xato urinishdan keyin 10 daqiqa blok), chiqim belgisi, oshxonaga "bekor" tiketi, audit | Bajarildi |
| R3.4 Chegirma (rol limiti, sabab, tasdiq), xizmat haqi (zal yoki korxona foizi, chegirmadan keyin) | Bajarildi. Qatorga chegirma va choy puli R5 da |
| Optimistik qulf (`version`, 409 `ORDER_CHANGED`) | Bajarildi |
| `/admin/restaurant/orders` sahifasi (zal sxemasi, chek, menyu, tasdiq oynasi, pre-chek chop etish, "Mening PIN") | Bajarildi |
| R5.1-R5.2 To'lov: aralash to'lov, qaytim (faqat naqddan), choy puli, `Sale` yaratish (`create_sale` orqali: kassa, smena, hamyon), xizmat haqi alohida "Xizmat haqi" qatori, chegirma sotuvga | Bajarildi |
| Fiskal chek: mavjud mahalliy modul (`fiskalSend`/`fiskalId` sozlamasi), chegirma taom qatorlariga taqsimlanadi, natija `PATCH /sales/{id}/fiscal` | Bajarildi. "Xizmat haqi" mahsulotiga MXIK kodini korxona kiritadi |
| R7.1 Ingredientlarni yechish: sotuv paytidagi tex karta versiyasi, filial "Oshxona" omboridan; `paid` va `sent` rejimlari; yarim tayyor qoldig'i yetmasa o'z kartasi bo'yicha yoyiladi; taom tannarxi sotuv qatoriga | Bajarildi |
| R7.3 Tayyorlangan taom bekor qilinsa chiqim (`rest_writeoff`), pishmagani `sent` rejimida omborga qaytadi | Bajarildi |
| Taom, modifikator va xizmat haqi qatorlarining o'z qoldig'i yo'q (`sale_create` ularni yechmaydi, oddiy POS'da ham) | Bajarildi |
| Restoran sotuvini umumiy qaytarish va o'chirish yo'llaridan himoya (409 `RESTAURANT_SALE`, `RESTAURANT_ITEM`) | Bajarildi |
| R5.4 Restoran chekini qaytarish (pul qaytadi, tayyorlangan taom omborga qaytmaydi) | Bajarildi: to'liq va qatorlar bo'yicha, chegirma va xizmat haqi ulushi, tovar faqat belgilansa omborga, menejer PIN, fiskal qaytarish cheki, "Bugun yopilgan cheklar" |
| R5.2 Hisobni bo'lish: teng (N kishiga, har qator miqdori 0.001 aniqlikda bo'linadi) va taomlar / mehmonlar bo'yicha (qatorning bir qismini ham); har bir qism alohida chek (`split_from_id`), alohida to'lov, sotuv va fiskal chek; oshxona holati va yechilgan ingredientlar mutanosib bo'linadi (qayta yechilmaydi), foizli chegirma o'tadi, summali chegirma mutanosib taqsimlanadi | Bajarildi |
| Hisobotlar 1, 2, 4, 8: kunlik ko'rsatkichlar, to'lov va buyurtma turlari, taomlar (haqiqiy tannarx, food cost), ofitsiantlar, bekor qilishlar, chegirmalar `/admin/restaurant/reports` | Bajarildi |
| R4.2 Oshxona ekrani (KDS) `/admin/restaurant/kds`: sex filtri, kartochkalar, norma bo'yicha kechikish (rang va yozuv), bir xil taomlar yig'indisi, bir yo'la "boshlash/tayyor", yaqinda bekor qilinganlar, ofitsiantga "taom tayyor" xabari; 5 soniyalik yangilanish (WebSocket keyin) | Bajarildi |
| R4.1 Oshxona printeri: chop etish navbati API (`/restaurant/print/queue`, atomar `claim`, `reprint`, `recent`; sex filtri, so'nggi 12 soat) va brauzerdagi "Chop etish stansiyasi" `/admin/restaurant/print` (sexlarni tanlash, 58/80 mm, 3 soniyalik avtomatik chop etish, bekor qilish tiketi, qayta chop etish, Chrome `--kiosk-printing` bilan dialogsiz). ESC/POS to'g'ridan-to'g'ri E-Code POS Restoran (R5.0) da shu API orqali | Bajarildi |
| R1.3 Qo'shimchalar (modifikatorlar): guruhlar (eng kam / eng ko'p tanlov, majburiy), variant narxi va ombordan yechiladigan bog'langan mahsulot, taomga biriktirish (Menyu: "Qo'shimchalar" bo'limi va taom qatoridagi tugma), buyurtmada tanlash oynasi va qoralamada o'zgartirish, narx chek / fiskal / sotuvga kiradi, tanlov surati saqlanadi, oshxona tiketi, KDS va chop etishda ko'rinadi, to'lovda bog'langan mahsulot oshxona omboridan yechiladi va tannarxga kiradi | Bajarildi |
| R1.5 Stop-list `/admin/restaurant/stop-list`: filial bo'yicha qo'lda to'xtatish (sabab, kim, qachongacha: 1 soat, 3 soat, kun oxiri, tanlangan vaqt; muddat o'tsa o'zi qaytadi), porsiya hisoblagichi (chekka qo'shishda kamayadi, qoralama o'chirilsa / miqdor kamaysa / pishmagan taom bekor qilinsa qaytadi), ingredient yetishmasligi (oshxona qoldig'i tex karta bo'yicha, yarim tayyor yoyiladi) va `auto_stop_on_no_stock` sozlamasi; buyurtma ekranida STOP / "qoldi N" / "ingredient kam", backend chekka qo'shishda qayta tekshiradi. Telegram menyu keyin shu API'dan oladi | Bajarildi |
| R6.1 Ofitsiant plansheti (PWA) `/waiter`: menejer "Ofitsiant planshetlari" `/admin/restaurant/terminals` bo'limida planshetni ulaydi (maxfiy havola bir marta, bazada SHA-256 xesh, bekor qilish), planshetda xodim ismini tanlab PIN bilan kiradi (faqat shu filialga ruxsati bor, cheklar yoki oshxona bilan ishlaydigan, PIN o'rnatgan xodimlar; 5 xato urinishdan keyin 10 daqiqa blok), sessiya 12 soat va planshetga bog'langan (`term` claim, planshet o'chirilsa darhol yaroqsiz), 3 daqiqa harakatsizlikda qulflanadi; ish ekrani mavjud buyurtmalar sahifasi, "Bosh ekranga qo'shish" uchun manifest | Bajarildi |
| R6.2 Alohida Flutter ilova "E-Code Ofitsiant" (`Desktop\ecode-ofitsiant-mobile`, paket `uz.ecode.ofitsiant`, APK 1.0.0; repodagi `mobile/` bu Marketplace Agent ilovasi, unga qo'shilmadi): planshetni havola bilan ulash, xodim tanlash va PIN, 3 daqiqada qulf, zal (stollar holati, mening stolim, "taom tayyor" xabari va tebranish), chek ochish, cheklarim va olib ketish, chek (qo'shimchalar, izoh, miqdor, kurs bo'yicha yuborish, "Berildi", bekor qilish), pre-chek, menyu (stop-list, qo'shimchalar). To'lov kassada (fiskal qurilma kassada) | Bajarildi (telefonda sinalmagan) |
| 10-bo'lim rollar: tayyor rollar (Ofitsiant, Oshpaz, Kassir (restoran), Zal menejeri) yangi restoranda avtomatik, mavjudlari uchun "Restoran rollarini qo'shish" tugmasi; Rollar sahifasida "Restoran" bo'limi (kalitlar, chegirma limiti, shablon) | Bajarildi |
| R7.2 Yarim tayyor tayyorlash `/admin/restaurant/production`: yarim tayyor va miqdor ("10 kg qiyma"), tex karta bo'yicha kerakli xom ashyo, oshxonadagi qoldiq, yetishmovchilik va tannarx oldindan ko'rinadi; xom ashyo filial "Oshxona" omboridan yechiladi, yarim tayyor shu omborga kiradi (bitta `production_orders` yozuvi, `manufacturing` paketi talab qilinmaydi); ichidagi yarim tayyor yetmasa o'z kartasi bo'yicha yoyiladi; xom ashyo yetmasa ogohlantirish va "Baribir tayyorlash" (qoldiq minusga); yarim tayyor tannarxi oxirgi tayyorlash bo'yicha; tarix (davr, yechilgan xom ashyo) va rahbar bekor qilishi (qoldiq qaytadi). Ruxsat: oshxona huquqi yoki omborchi | Bajarildi |
| R7.5 Tannarxni qayta hisoblash: tex karta tannarxi har doim joriy ingredient narxidan; xarid qabuli (va darhol qabul qilingan xarid), qo'lda kirim va menyuda tannarx tahririda narxi o'zgargan ingredient ishlatiladigan taom va yarim tayyorlar (ichma-ich kartalar orqali ham) eski / yangi tannarx va food cost % bilan `restaurant_cost_changes` ga yoziladi; xarid qabulidan keyin "N ta taom tannarxi o'zgardi, M tasi chegaradan oshdi" xabari; "Food cost" sahifasi `/admin/restaurant/food-cost`: chegaradan oshgan taomlar (tavsiya narx bilan) va o'zgarishlar tarixi. Ko'rish: admin, direktor, menejer, buxgalter, omborchi | Bajarildi |
| R8.1 Bron `/admin/restaurant/reservations`: kun jadvali (stollar x soatlar) va ro'yxat; stol(lar), vaqt, davomiylik (sukut 2 soat), mehmonlar, ism, telefon (mijoz telefon bo'yicha bog'lanadi), izoh; bir stolga vaqt kesishsa 409 (faol: kutilayotgan va cheki yopilmagan kelgan); holatlar kutilmoqda / keldi (chek ochiladi) / kelmadi / bekor. Depozit bron paytida kassaga kirim qilinadi, chek yopilganda `deposit` to'lov qatori (kassaga qayta kirim yo'q, fiskal chekda asl to'lov usuli), ortig'i qaytariladi; bekor qilishda qaytarish, kelmasa qoladi. Zal sxemasida "Bron" holati (bron vaqtidan 60 daqiqa oldin) va vaqt belgisi, stol bosilsa "Mehmon keldi"; to'lov oynasida depozit. Eslatma bron vaqtidan 2 soat oldin: Telegram (korxona boti, mijoz chat_id), bo'lmasa sozlamada yoqilsa SMS; har bron bir marta. Ofitsiant ilovasi 1.0.1 da ham bron belgisi va "Mehmon keldi" | Bajarildi |
| Hisobotlar 3, 5, 6, 7, 9 va R7.4 sarf tahlili (`/admin/restaurant/reports`, yangi bo'limlar; `GET /restaurant/reports/analytics`): menyu muhandisligi (Kasavana-Smith: mashhurlik 70% x 1/N, foydalilik o'rtacha porsiya foydasi; yulduz, ishchi ot, jumboq, zaif va har biriga tavsiya); yuklama xaritasi (hafta kuni x soat, Toshkent vaqti: cheklar, tushum, mehmonlar; eng band vaqt); stol aylanishi (stol bo'yicha band bo'lish, kuniga, o'rtacha o'tirish vaqti, bir o'ringa tushum, bo'sh turgan stollar); oshxona tezligi (yuborishdan tayyorgacha o'rtacha va P90, navbatda kutish, tex karta me'yoridan kechikish; sex va taom bo'yicha); ombor (oshxona ombori: qoldiq va qiymat, tex karta bo'yicha nazariy sarf: sotuv va yarim tayyor tayyorlash, chiqim, inventarizatsiya farqi, haqiqiy sarf, farq foizi va summasi, manfiy qoldiqlar) | Bajarildi |
| Restoran bosh sahifasi `/admin/restaurant/dashboard` (`GET /restaurant/reports/dashboard`, 30 soniyada yangilanadi): bugungi tushum, ochiq cheklar va summasi, band stollar, hisob so'ralganlar, oshxona navbati va tayyor-berilmaganlar, tex karta me'yoridan kechikayotgan taomlar (sex bo'yicha), bugungi bronlar, stop-list va ingredient yetmaydigan taomlar; filial yoki barcha filiallar. Ochilish sahifasi o'zgarmadi (zal) | Bajarildi |
| R1.2 Tex kartalar Excel eksport va import (Menyu: taomlar va yarim tayyor bo'limlarida "Excel eksport", "Excel import", "Shablon"): bir qator bitta ingredient; taom va ingredient kodi yoki nomi bo'yicha (bir xil nomli bir nechta bo'lsa xato), ustun nomlari uch tilda taniladi; avval tekshirish (hech narsa saqlanmaydi), keyin import; yo'q taom va ingredientni yaratish ixtiyoriy; yarim tayyor taomdan oldin; o'zgarmagan karta yangi versiya ochmaydi; har karta alohida saqlanadi, qator xatolari ro'yxati | Bajarildi |
| R9.1 Super Admin "Restoranlar" bo'limi (format, filiallar, tarif va obuna, oxirgi faollik, bugungi cheklar va tushum, ochiq cheklar, planshetlar, imkoniyatlar) va restoran tariflari: `tariffs.business_type` bo'yicha ro'yxat ajratilgan, boshqa turdagi tarifni sotib olish yoki biriktirish rad (`TARIFF_TYPE_MISMATCH`); tarifda ofitsiant planshetlari limiti (`TARIFF_LIMIT`), KDS ekranlari soni va imkoniyatlar (KDS, bron, yetkazish, agregatorlar, QR menyu: kirmagani 403 va menyuda yashiriladi, ro'yxat belgilanmasa cheklov yo'q); sinov tarifi korxona turi bo'yicha; migratsiya `r9_1` boshlang'ich tariflar (Restoran sinov, Kafe 40%, Restoran 70%, Tarmoq 95%; imkoniyat va qurilma limitlari Super Admin'da belgilanadi) | Bajarildi |
| R5.0 E-Code POS Restoran (Windows ilova, `Desktop\e-code-pos-restoran`, 1.0.0; dorixona E-Code POS asosida, ekranlar yangidan): kirish (oflayn ham), filial, zal, chek, menyu, qo'shimchalar, stop-list, oshxonaga, pre-chek, to'lov (aralash, choy puli, depozit), fiskal modul, menejer PIN tasdig'i; onlayn paytda chop etish stansiyasi; internet uzilsa chek ochish, oshxona tiketi, to'lov va fiskal chek lokal, navbat `POST /restaurant/offline/sync` (op_id bilan idempotent, oflayn vaqtlar, tiketlar qayta chop etilmaydi, to'lov qayta yozilmaydi), `GET /restaurant/offline/bootstrap`; o'rnatuvchi `pos-updates/apps/` va avtoyangilanish kanali `pos-updates/restoran/`. Oflayn mumkin emas: yuborilgan taomni bekor qilish, chegirma, ko'chirish, qaytarish | Bajarildi (haqiqiy printer va fiskal qurilmada sinalmagan) |

Ruxsatlar (`restaurant` bo'limi, rol ruxsatlarida yoki xodimning shaxsiy ruxsatlarida): `orders`, `all_tables`,
`cancel_sent`, `discount_max` (foiz), `unlock_precheck`, `move_table`, `kitchen`, `take_payment`, `waiter`.
Sukut: admin, direktor, menejer hammasi; kassir cheklar, ko'chirish va to'lov, bekor qilish va chegirma tasdiq bilan.
Ofitsiant uchun maxsus rolga `waiter: true` beriladi: "hamma stollar" va "to'lov olish" restoran sozlamasidan.
