import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import '../api/api_client.dart';
import 'home_screen.dart';

class CategoriesScreen extends StatefulWidget {
  final bool isInitialSelection;
  const CategoriesScreen({super.key, this.isInitialSelection = true});

  @override
  State<CategoriesScreen> createState() => _CategoriesScreenState();
}

class _CategoriesScreenState extends State<CategoriesScreen> {
  List<dynamic> _allCategories = [];
  Set<int> _selectedIds = {};
  bool _loading = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _fetchData();
  }

  Future<void> _fetchData() async {
    try {
      // Fetch all available categories
      final catResp = await apiClient.dio.get('/mobile/marketplace/categories');
      // Fetch user's currently selected categories
      final profileResp = await apiClient.dio.get('/mobile/marketplace/me');
      
      final currentCats = profileResp.data['categories'] as List<dynamic>;
      final preselected = currentCats.map<int>((c) => c['id'] as int).toSet();

      setState(() {
        _allCategories = catResp.data['items'] ?? [];
        _selectedIds = preselected;
        _loading = false;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Xatolik: $e')),
        );
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _saveCategories() async {
    if (_selectedIds.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Kamida bitta kategoriya tanlang')),
      );
      return;
    }

    setState(() => _saving = true);
    try {
      await apiClient.dio.put('/mobile/marketplace/my-categories', data: {
        'category_ids': _selectedIds.toList(),
      });
      
      if (!mounted) return;
      
      if (widget.isInitialSelection) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const HomeScreen()),
        );
      } else {
        Navigator.of(context).pop(true); // Return to previous with success
      }
    } on DioException catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.response?.data['detail'] ?? 'Xatolik yuz berdi')),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Kategoriyalar'),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                const Padding(
                  padding: EdgeInsets.all(16.0),
                  child: Text(
                    'Siz qaysi yo\'nalishlarda (kategoriyalarda) savdo qilasiz? Keraklilarini belgilang:',
                    style: TextStyle(fontSize: 16),
                  ),
                ),
                Expanded(
                  child: ListView.builder(
                    itemCount: _allCategories.length,
                    itemBuilder: (context, index) {
                      final cat = _allCategories[index];
                      final catId = cat['id'] as int;
                      final catName = cat['name'] ?? 'Noma\'lum';
                      final isSelected = _selectedIds.contains(catId);

                      return CheckboxListTile(
                        title: Text(catName),
                        value: isSelected,
                        onChanged: (val) {
                          setState(() {
                            if (val == true) {
                              _selectedIds.add(catId);
                            } else {
                              _selectedIds.remove(catId);
                            }
                          });
                        },
                      );
                    },
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: _saving ? null : _saveCategories,
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                      child: _saving
                          ? const CircularProgressIndicator()
                          : const Text('Saqlash va Davom etish', style: TextStyle(fontSize: 18)),
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}
