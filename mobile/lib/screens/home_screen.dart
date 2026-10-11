import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../api/api_client.dart';
import 'login_screen.dart';
import 'categories_screen.dart';
import 'add_product_screen.dart';
import 'my_products_screen.dart';
import 'transactions_screen.dart';
import 'notifications_screen.dart';
import 'profile_screen.dart';
import 'package:dio/dio.dart';
import 'package:url_launcher/url_launcher.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _currentIndex = 0;
  Map<String, dynamic>? _profile;
  Map<String, dynamic>? _balance;
  int _unreadCount = 0;
  bool _loading = true;
  bool _isLaunching = false;
  int _selectedMonths = 1; // 1, 3, 6 oy
  Timer? _notifTimer;

  @override
  void initState() {
    super.initState();
    _fetchData();
    // Har 25 soniyada yangi bildirishnomalarni tekshirib, ovoz chiqarish
    _notifTimer = Timer.periodic(const Duration(seconds: 25), (_) {
      _pollNotifications();
    });
  }

  @override
  void dispose() {
    _notifTimer?.cancel();
    super.dispose();
  }

  Future<void> _pollNotifications() async {
    try {
      final notifResp = await apiClient.dio.get('/mobile/marketplace/notifications');
      final unread = notifResp.data['unread_count'] ?? 0;
      if (unread > _unreadCount) {
        SystemSound.play(SystemSoundType.alert);
        HapticFeedback.heavyImpact();
      }
      if (mounted) {
        setState(() => _unreadCount = unread);
      }
    } catch (_) {}
  }

  Future<void> _fetchData() async {
    try {
      final profileResp = await apiClient.dio.get('/mobile/marketplace/me');
      Map<String, dynamic>? balance;
      try {
        final balanceResp = await apiClient.dio.get('/mobile/marketplace/balance');
        balance = balanceResp.data;
      } catch (_) {}

      int unread = 0;
      try {
        final notifResp = await apiClient.dio.get('/mobile/marketplace/notifications');
        unread = notifResp.data['unread_count'] ?? 0;
      } catch (_) {}

      if (unread > _unreadCount && !_loading) {
        SystemSound.play(SystemSoundType.alert);
        HapticFeedback.heavyImpact();
      }

      setState(() {
        _profile = profileResp.data;
        _balance = balance;
        _unreadCount = unread;
        _loading = false;
      });
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) {
        await apiClient.clearToken();
        if (mounted) {
          Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const LoginScreen()));
        }
      } else {
        setState(() => _loading = false);
      }
    } catch (_) {
      setState(() => _loading = false);
    }
  }

  Future<void> _logout() async {
    await apiClient.clearToken();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
    );
  }

  Future<void> _payWithPayme([int? months]) async {
    final m = months ?? _selectedMonths;
    setState(() => _isLaunching = true);
    try {
      final res = await apiClient.dio.get(
        '/mobile/marketplace/auth/payme-checkout',
        queryParameters: {'months': m},
      );
      final url = Uri.parse(res.data['checkout_url']);
      bool launched = false;
      try {
        launched = await launchUrl(url, mode: LaunchMode.externalApplication);
      } catch (_) {}
      if (!launched) {
        try {
          launched = await launchUrl(url, mode: LaunchMode.inAppBrowserView);
        } catch (_) {}
      }
      if (!launched) {
        try {
          launched = await launchUrl(url, mode: LaunchMode.platformDefault);
        } catch (_) {}
      }
      if (!launched && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Havolani ochib bo\'lmadi')),
        );
      }
    } on DioException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Xatolik: ${e.response?.data['detail'] ?? e.message}')),
        );
      }
    } finally {
      if (mounted) setState(() => _isLaunching = false);
    }
  }

  Widget _buildDashboard() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_profile == null) return const Center(child: Text('Ma\'lumot yuklanmadi'));

    final status = _profile!['status'];
    final needsCategory = _profile!['needs_category_selection'] == true;

    if (status != 'active') {
      final plans = [
        {'months': 1, 'name': '1 oylik', 'price': '200,000 so\'m', 'desc': 'Standart oylik obuna', 'badge': ''},
        {'months': 3, 'name': '3 oylik', 'price': '550,000 so\'m', 'desc': '50,000 so\'m tejaladi (~183k/oy)', 'badge': 'Ommabop'},
        {'months': 6, 'name': '6 oylik', 'price': '1,000,000 so\'m', 'desc': '200,000 so\'m tejaladi (~166k/oy)', 'badge': 'Eng foydali'},
      ];

      final selectedPlan = plans.firstWhere((p) => p['months'] == _selectedMonths);

      return Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.blue.shade50,
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.workspace_premium, size: 52, color: Color(0xFF2563EB)),
              ),
              const SizedBox(height: 16),
              const Text(
                'Hisobingizni faollashtiring',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 6),
              const Text(
                'Savdo qilish uchun qulay tarif muddatini tanlang:',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 14, color: Colors.black54),
              ),
              const SizedBox(height: 20),
              ...plans.map((p) {
                final isSelected = _selectedMonths == p['months'];
                return Padding(
                  padding: const EdgeInsets.only(bottom: 12.0),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(16),
                    onTap: () => setState(() => _selectedMonths = p['months'] as int),
                    child: Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: isSelected ? const Color(0xFFEFF6FF) : Colors.white,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: isSelected ? const Color(0xFF2563EB) : Colors.grey.shade300,
                          width: isSelected ? 2 : 1,
                        ),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            isSelected ? Icons.radio_button_checked : Icons.radio_button_off,
                            color: isSelected ? const Color(0xFF2563EB) : Colors.grey.shade400,
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Text(
                                      p['name'] as String,
                                      style: TextStyle(
                                        fontSize: 16,
                                        fontWeight: FontWeight.bold,
                                        color: isSelected ? const Color(0xFF1E3A8A) : Colors.black87,
                                      ),
                                    ),
                                    if ((p['badge'] as String).isNotEmpty) ...[
                                      const SizedBox(width: 8),
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                        decoration: BoxDecoration(
                                          color: p['months'] == 6 ? Colors.amber.shade100 : Colors.blue.shade100,
                                          borderRadius: BorderRadius.circular(8),
                                        ),
                                        child: Text(
                                          p['badge'] as String,
                                          style: TextStyle(
                                            fontSize: 10,
                                            fontWeight: FontWeight.bold,
                                            color: p['months'] == 6 ? Colors.amber.shade900 : const Color(0xFF1D4ED8),
                                          ),
                                        ),
                                      ),
                                    ],
                                  ],
                                ),
                                const SizedBox(height: 3),
                                Text(
                                  p['desc'] as String,
                                  style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                                ),
                              ],
                            ),
                          ),
                          Text(
                            p['price'] as String,
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.bold,
                              color: isSelected ? const Color(0xFF2563EB) : Colors.black87,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              }),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                height: 52,
                child: ElevatedButton.icon(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF2563EB),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                    elevation: 2,
                  ),
                  onPressed: _isLaunching ? null : () => _payWithPayme(_selectedMonths),
                  icon: _isLaunching
                      ? const SizedBox.shrink()
                      : const Icon(Icons.payment, color: Colors.white),
                  label: _isLaunching
                      ? const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2.5),
                        )
                      : Text(
                          'Payme orqali to\'lash (${selectedPlan['price']})',
                          style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.bold),
                        ),
                ),
              ),
              const SizedBox(height: 12),
              TextButton.icon(
                onPressed: _fetchData,
                icon: const Icon(Icons.refresh, size: 18),
                label: const Text('To\'lov holatini yangilash'),
              ),
            ],
          ),
        ),
      );
    }

    if (needsCategory) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text('Kategoriyangizni tanlang', style: TextStyle(fontSize: 20)),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const CategoriesScreen(isInitialSelection: true)),
                );
              }, 
              child: const Text('Kategoriyalarga o\'tish'),
            ),
          ],
        ),
      );
    }

    final bal = _balance?['balance'] ?? 0.0;

    return RefreshIndicator(
      onRefresh: _fetchData,
      child: ListView(
        padding: const EdgeInsets.all(16.0),
        children: [
          InkWell(
            onTap: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const TransactionsScreen()),
              );
            },
            child: Card(
              color: Colors.blue.shade50,
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: Column(
                  children: [
                    const Text('Joriy Balans', style: TextStyle(fontSize: 16)),
                    const SizedBox(height: 8),
                    Text('$bal so\'m', style: const TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: Colors.blue)),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 24),
          const Text('Tezkor amallar', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _ActionButton(
                  icon: Icons.add_box,
                  label: 'Mahsulot\nqo\'shish',
                  onTap: () async {
                    final res = await Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const AddProductScreen()),
                    );
                    if (res == true) _fetchData();
                  },
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: _ActionButton(
                  icon: Icons.inventory,
                  label: 'Mening\nmahsulotlarim',
                  onTap: () {
                    setState(() => _currentIndex = 1);
                  },
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _currentIndex,
        children: [
          Scaffold(
            backgroundColor: const Color(0xFFF8FAFC),
            appBar: AppBar(
              title: const Text('Agent Dashboard', style: TextStyle(fontWeight: FontWeight.bold)),
              backgroundColor: Colors.white,
              elevation: 0,
              actions: [
                IconButton(
                  icon: Badge(
                    isLabelVisible: _unreadCount > 0,
                    label: Text('$_unreadCount'),
                    child: const Icon(Icons.notifications_outlined),
                  ),
                  onPressed: () async {
                    await Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const NotificationsScreen()),
                    );
                    _fetchData();
                  },
                ),
                IconButton(
                  icon: const Icon(Icons.refresh),
                  onPressed: _fetchData,
                ),
                IconButton(
                  icon: const Icon(Icons.logout),
                  tooltip: 'Chiqish',
                  onPressed: _logout,
                ),
              ],
            ),
            body: _buildDashboard(),
          ),
          const MyProductsScreen(isTab: true),
          const ProfileScreen(isTab: true),
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        selectedItemColor: const Color(0xFF2563EB),
        unselectedItemColor: const Color(0xFF94A3B8),
        onTap: (index) {
          setState(() => _currentIndex = index);
          if (index == 0) _fetchData();
        },
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.dashboard_outlined), activeIcon: Icon(Icons.dashboard), label: 'Asosiy'),
          BottomNavigationBarItem(icon: Icon(Icons.inventory_2_outlined), activeIcon: Icon(Icons.inventory_2), label: 'Mahsulotlarim'),
          BottomNavigationBarItem(icon: Icon(Icons.person_outline), activeIcon: Icon(Icons.person), label: 'Profil'),
        ],
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _ActionButton({required this.icon, required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          border: Border.all(color: Colors.grey.shade300),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          children: [
            Icon(icon, size: 32, color: Colors.blue),
            const SizedBox(height: 8),
            Text(label, textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}
