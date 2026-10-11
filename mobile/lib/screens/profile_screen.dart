import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../api/api_client.dart';
import 'login_screen.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  Map<String, dynamic>? _profile;
  Map<String, dynamic>? _balance;
  bool _loading = true;
  String _currentLanguage = 'uz'; // 'uz', 'ru', 'en'

  static const brandBlue = Color(0xFF2563EB);
  static const darkBlue = Color(0xFF1E3A8A);

  @override
  void initState() {
    super.initState();
    _loadLanguage();
    _fetchProfile();
  }

  Future<void> _loadLanguage() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _currentLanguage = prefs.getString('app_language') ?? 'uz';
    });
  }

  Future<void> _setLanguage(String lang) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('app_language', lang);
    setState(() {
      _currentLanguage = lang;
    });
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            lang == 'uz'
                ? 'Til o\'zgartirildi: O\'zbekcha'
                : lang == 'ru'
                    ? 'Язык изменен: Русский'
                    : 'Language changed: English',
          ),
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  Future<void> _fetchProfile() async {
    try {
      final pRes = await apiClient.dio.get('/mobile/marketplace/me');
      Map<String, dynamic>? bData;
      try {
        final bRes = await apiClient.dio.get('/mobile/marketplace/balance');
        bData = bRes.data;
      } catch (_) {}

      if (mounted) {
        setState(() {
          _profile = pRes.data;
          _balance = bData;
          _loading = false;
        });
      }
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) {
        await apiClient.clearToken();
        if (mounted) {
          Navigator.of(context).pushReplacement(
            MaterialPageRoute(builder: (_) => const LoginScreen()),
          );
        }
      } else {
        if (mounted) setState(() => _loading = false);
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _logout() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Hisobdan chiqish'),
        content: const Text('Rostdan ham profilingizdan chiqmoqchimisiz?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Bekor qilish'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Chiqish', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );

    if (confirm == true) {
      await apiClient.clearToken();
      if (mounted) {
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const LoginScreen()),
          (route) => false,
        );
      }
    }
  }

  void _showDocumentSheet(String title, String content) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => DraggableScrollableSheet(
        initialChildSize: 0.85,
        maxChildSize: 0.95,
        minChildSize: 0.5,
        expand: false,
        builder: (_, scrollCtrl) => Container(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 48,
                  height: 5,
                  decoration: BoxDecoration(
                    color: Colors.grey.shade300,
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
              ),
              const SizedBox(height: 18),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    title,
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Color(0xFF0F172A)),
                  ),
                  IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(ctx)),
                ],
              ),
              const Divider(),
              Expanded(
                child: ListView(
                  controller: scrollCtrl,
                  children: [
                    Text(
                      content,
                      style: const TextStyle(fontSize: 13, height: 1.6, color: Color(0xFF334155)),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _formatMoney(dynamic val) {
    final num numVal = val is num ? val : (double.tryParse(val?.toString() ?? '0') ?? 0);
    return NumberFormat('#,###', 'uz_UZ').format(numVal).replaceAll(',', ' ');
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator(color: brandBlue)),
      );
    }

    final name = _profile?['name'] ?? 'Savdo Agenti';
    final phone = _profile?['phone'] ?? '';
    final orgCode = _profile?['org_code'] ?? '0001';
    final companyName = _profile?['company_name'] ?? '';
    final status = _profile?['status'] ?? 'pending';
    final isActive = status == 'active';

    final totalGoodsValue = _balance?['goods_total_value'] ?? 0;
    final totalGoodsQty = _balance?['goods_qty'] ?? 0;
    final warehouseDebt = _balance?['warehouse_debt'] ?? 0;
    final currentBalance = _balance?['balance'] ?? 0;
    final sales = _balance?['sales'] ?? 0;

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text('Profil va Hisob', style: TextStyle(fontWeight: FontWeight.w700)),
        backgroundColor: Colors.white,
        elevation: 0,
        scrolledUnderElevation: 1,
        actions: [
          IconButton(
            icon: const Icon(Icons.logout, color: Colors.redAccent),
            tooltip: 'Chiqish',
            onPressed: _logout,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _fetchProfile,
        color: brandBlue,
        child: ListView(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
          children: [
            // User Header Card
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [brandBlue, darkBlue],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(20),
                boxShadow: [
                  BoxShadow(
                    color: brandBlue.withValues(alpha: 0.3),
                    blurRadius: 16,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              child: Row(
                children: [
                  Container(
                    width: 64,
                    height: 64,
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.2),
                      shape: BoxShape.circle,
                      border: Border.all(color: Colors.white, width: 2),
                    ),
                    child: const Icon(Icons.person, color: Colors.white, size: 36),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          phone.startsWith('+') ? phone : '+$phone',
                          style: TextStyle(color: Colors.white.withValues(alpha: 0.85), fontSize: 13),
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: 0.25),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(Icons.key, color: Colors.white, size: 12),
                                  const SizedBox(width: 4),
                                  Text(
                                    'Maxsus kod: $orgCode',
                                    style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                              decoration: BoxDecoration(
                                color: isActive ? const Color(0xFF10B981) : Colors.amber.shade700,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                isActive ? 'Faol' : 'Kutilmoqda',
                                style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            if (companyName.isNotEmpty) ...[
              const SizedBox(height: 8),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: Text(
                  'Biriktirilgan korxona: $companyName',
                  style: const TextStyle(fontSize: 12, color: Color(0xFF64748B), fontWeight: FontWeight.w600),
                ),
              ),
            ],

            const SizedBox(height: 20),

            // Sklad va Qarz hisobi (Mir-maza skladiga berilgan tovarlar)
            const Text(
              'SKLAD VA BALANS STATISTIKASI',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: Color(0xFF475569), letterSpacing: 0.8),
            ),
            const SizedBox(height: 10),

            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFFE2E8F0)),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.03),
                    blurRadius: 10,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Column(
                children: [
                  // Mir-maza skladiga berilgan tovarlar
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: const Color(0xFFEFF6FF),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Icon(Icons.warehouse_outlined, color: brandBlue, size: 24),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Mir-maza skladiga topshirilgan',
                              style: TextStyle(fontSize: 12, color: Color(0xFF64748B), fontWeight: FontWeight.w600),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              '${_formatMoney(totalGoodsValue)} so\'m',
                              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: Color(0xFF0F172A)),
                            ),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF1F5F9),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          '$totalGoodsQty dona',
                          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF334155)),
                        ),
                      ),
                    ],
                  ),
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 12),
                    child: Divider(color: Color(0xFFF1F5F9), height: 1),
                  ),

                  // Sklad qarzi (Olinishi kerak bo'lgan summa)
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFEF3C7),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Icon(Icons.request_quote_outlined, color: Color(0xFFD97706), size: 24),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Sklad qarzi (Olinishi kerak)',
                              style: TextStyle(fontSize: 12, color: Color(0xFF64748B), fontWeight: FontWeight.w600),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              '${_formatMoney(warehouseDebt)} so\'m',
                              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: Color(0xFFD97706)),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),

                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 12),
                    child: Divider(color: Color(0xFFF1F5F9), height: 1),
                  ),

                  // Joriy sotuv balansi
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: const Color(0xFFECFDF5),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Icon(Icons.account_balance_wallet_outlined, color: Color(0xFF059669), size: 24),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Joriy hisob balansi',
                              style: TextStyle(fontSize: 12, color: Color(0xFF64748B), fontWeight: FontWeight.w600),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              '${_formatMoney(currentBalance)} so\'m',
                              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: Color(0xFF059669)),
                            ),
                          ],
                        ),
                      ),
                      Text(
                        'Sotuv: ${_formatMoney(sales)}',
                        style: const TextStyle(fontSize: 11, color: Color(0xFF64748B), fontWeight: FontWeight.w600),
                      ),
                    ],
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            // Tillar bo'limi (Language Switcher)
            const Text(
              'ILOVA TILI',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: Color(0xFF475569), letterSpacing: 0.8),
            ),
            const SizedBox(height: 10),

            Container(
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Column(
                children: [
                  RadioListTile<String>(
                    title: const Row(
                      children: [
                        Text('🇺🇿', style: TextStyle(fontSize: 20)),
                        SizedBox(width: 12),
                        Text('O\'zbekcha', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                      ],
                    ),
                    value: 'uz',
                    activeColor: brandBlue,
                    groupValue: _currentLanguage,
                    onChanged: (val) => _setLanguage(val!),
                  ),
                  const Divider(height: 1, indent: 54),
                  RadioListTile<String>(
                    title: const Row(
                      children: [
                        Text('🇷🇺', style: TextStyle(fontSize: 20)),
                        SizedBox(width: 12),
                        Text('Русский', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                      ],
                    ),
                    value: 'ru',
                    activeColor: brandBlue,
                    groupValue: _currentLanguage,
                    onChanged: (val) => _setLanguage(val!),
                  ),
                  const Divider(height: 1, indent: 54),
                  RadioListTile<String>(
                    title: const Row(
                      children: [
                        Text('🇬🇧', style: TextStyle(fontSize: 20)),
                        SizedBox(width: 12),
                        Text('English', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                      ],
                    ),
                    value: 'en',
                    activeColor: brandBlue,
                    groupValue: _currentLanguage,
                    onChanged: (val) => _setLanguage(val!),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            // Yuridik hujjatlar
            const Text(
              'HUJJATLAR VA SIYOSAT',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: Color(0xFF475569), letterSpacing: 0.8),
            ),
            const SizedBox(height: 10),

            Container(
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Column(
                children: [
                  ListTile(
                    leading: const Icon(Icons.description_outlined, color: brandBlue),
                    title: const Text('Ommaviy oferta', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                    trailing: const Icon(Icons.chevron_right, color: Color(0xFF94A3B8)),
                    onTap: () => _showDocumentSheet(
                      'Ommaviy Oferta',
                      'Savdo agentlari bilan hamkorlik qilish bo\'yicha\nOMMAVIY OFERTA SHARTNOMASI\n\n'
                      '1. Umumiy qoidalar\n'
                      '1.1. Mazkur hujjat E-Code ERP va Mir-Maza marketplace tizimida faoliyat yurituvchi savdo agentlari uchun rasmiy taklif (ommaviy oferta) hisoblanadi.\n'
                      '1.2. Ilovada ro\'yxatdan o\'tish va tizimdan foydalanish orqali Agent ushbu shartnoma shartlarini to\'liq va so\'zsiz qabul qiladi.\n\n'
                      '2. Mahsulotlar va Sklad\n'
                      '2.1. Agent tomonidan qo\'shilgan mahsulotlar korxona admini tomonidan moderatsiyadan o\'tkaziladi.\n'
                      '2.2. Tasdiqlangan mahsulotlar ERP omboriga kirim (prixod) qilinadi va Mir-maza marketplaciga sinxronlanadi.\n\n'
                      '3. Moliyaviy hisob-kitoblar\n'
                      '3.1. Sotilgan tovarlar uchun hisob-kitoblar belgilangan muddatlarda Payme yoki bank o\'tkazmasi orqali to\'lanadi.\n'
                      '3.2. Agent qoldiq tovarlar va hisob-kitoblarni ilova orqali real vaqtda ko\'rib turadi.',
                    ),
                  ),
                  const Divider(height: 1, indent: 56),
                  ListTile(
                    leading: const Icon(Icons.shield_outlined, color: brandBlue),
                    title: const Text('Maxfiylik siyosati', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                    trailing: const Icon(Icons.chevron_right, color: Color(0xFF94A3B8)),
                    onTap: () => _showDocumentSheet(
                      'Maxfiylik Siyosati',
                      'MAXFIYLIK VA SHAXSIY MA\'LUMOTLARNI HIMOYA QILISH SIYOSATI\n\n'
                      '1. Ma\'lumotlarni yig\'ish va ulardan foydalanish\n'
                      '1.1. E-Code tizimi foydalanuvchilarning telefon raqami, ismi va hisob-kitob ma\'lumotlarini xavfsiz holda saqlaydi.\n'
                      '1.2. Ushbu ma\'lumotlar faqatgina tizim xizmatlarini ko\'rsatish, buyurtmalarni boshqarish va to\'lovlarni hisob-kitob qilish uchun ishlatiladi.\n\n'
                      '2. Ma\'lumotlar xavfsizligi\n'
                      '2.1. Barcha parollar va shaxsiy ma\'lumotlar zamonaviy kriptografik standartlar orqali shifrlanadi.\n'
                      '2.2. Foydalanuvchi ma\'lumotlari uchinchi shaxslarga berilmaydi.',
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            // Logout Button
            SizedBox(
              height: 50,
              child: OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: Color(0xFFFCA5A5)),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  backgroundColor: const Color(0xFFFEF2F2),
                ),
                icon: const Icon(Icons.logout, color: Colors.red),
                label: const Text('Hisobdan chiqish', style: TextStyle(color: Colors.red, fontWeight: FontWeight.w700)),
                onPressed: _logout,
              ),
            ),

            const SizedBox(height: 20),
            Center(
              child: Text(
                'E-Code Agent v1.0.0 • E-Code ERP & Mir-Maza',
                style: TextStyle(fontSize: 11, color: Colors.grey.shade400, fontWeight: FontWeight.w500),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
