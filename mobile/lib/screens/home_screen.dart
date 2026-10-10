import 'package:flutter/material.dart';
import '../api/api_client.dart';
import 'login_screen.dart';
import 'categories_screen.dart';
import 'add_product_screen.dart';
import 'my_products_screen.dart';
import 'transactions_screen.dart';
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
  bool _loading = true;
  bool _isLaunching = false;

  @override
  void initState() {
    super.initState();
    _fetchData();
  }

  Future<void> _fetchData() async {
    try {
      final profileResp = await apiClient.dio.get('/mobile/marketplace/me');
      Map<String, dynamic>? balance;
      try {
        final balanceResp = await apiClient.dio.get('/mobile/marketplace/balance');
        balance = balanceResp.data;
      } catch (_) {}
      setState(() {
        _profile = profileResp.data;
        _balance = balance;
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

  Future<void> _payWithPayme() async {
    setState(() => _isLaunching = true);
    try {
      final res = await apiClient.dio.get('/mobile/marketplace/auth/payme-checkout');
      final url = Uri.parse(res.data['checkout_url']);
      if (!await launchUrl(url, mode: LaunchMode.externalApplication)) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Havolani ochib bo\'lmadi')),
          );
        }
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
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.payment, size: 64, color: Colors.blue),
              const SizedBox(height: 16),
              const Text('Hisobingiz faol emas', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              const Text(
                'Tizimdan foydalanish uchun 200,000 so\'m to\'lov qilishingiz kerak.', 
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 16)
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.teal),
                  onPressed: _isLaunching ? null : _payWithPayme, 
                  child: _isLaunching 
                      ? const CircularProgressIndicator(color: Colors.white)
                      : const Text('Payme orqali to\'lash', style: TextStyle(color: Colors.white, fontSize: 18)),
                ),
              ),
              const SizedBox(height: 16),
              TextButton(onPressed: _fetchData, child: const Text('Holatni yangilash')),
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
                    Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const MyProductsScreen()),
                    );
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
      appBar: AppBar(
        title: const Text('Agent Dashboard'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: _logout,
          ),
        ],
      ),
      body: _buildDashboard(),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (index) {
          setState(() => _currentIndex = index);
          if (index == 1) {
            Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const CategoriesScreen(isInitialSelection: false)),
            ).then((_) {
              setState(() => _currentIndex = 0);
              _fetchData();
            });
          }
        },
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.dashboard), label: 'Asosiy'),
          BottomNavigationBarItem(icon: Icon(Icons.category), label: 'Kategoriyalar'),
          BottomNavigationBarItem(icon: Icon(Icons.person), label: 'Profil'),
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
