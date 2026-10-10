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
    final allSelected = _allCategories.isNotEmpty && _selectedIds.length == _allCategories.length;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Kategoriyalar'),
        actions: [
          if (!_loading && _allCategories.isNotEmpty)
            TextButton(
              onPressed: () {
                setState(() {
                  if (allSelected) {
                    _selectedIds.clear();
                  } else {
                    _selectedIds = _allCategories.map<int>((c) => c['id'] as int).toSet();
                  }
                });
              },
              child: Text(
                allSelected ? 'Tozalash' : 'Barchasi',
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _allCategories.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.category_outlined, size: 64, color: Colors.grey),
                      const SizedBox(height: 16),
                      const Text('Kategoriyalar topilmadi', style: TextStyle(fontSize: 16)),
                      const SizedBox(height: 12),
                      ElevatedButton(onPressed: _fetchData, child: const Text('Qayta yuklash')),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _fetchData,
                  child: Column(
                    children: [
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 12.0),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                'Qaysi kategoriyalarda savdo qilasiz? (${_selectedIds.length}/${_allCategories.length} tanlandi)',
                                style: const TextStyle(fontSize: 14, color: Colors.black87),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const Divider(height: 1),
                      Expanded(
                        child: ListView.separated(
                          itemCount: _allCategories.length,
                          separatorBuilder: (ctx, i) => const Divider(height: 1, indent: 64),
                          itemBuilder: (context, index) {
                            final cat = _allCategories[index];
                            final catId = cat['id'] as int;
                            final catName = cat['name'] ?? 'Noma\'lum';
                            final isSelected = _selectedIds.contains(catId);
                            final icon = cat['icon'] as String?;
                            final image = cat['image'] as String?;

                            Widget leadingWidget;
                            if (image != null && image.isNotEmpty) {
                              leadingWidget = ClipRRect(
                                borderRadius: BorderRadius.circular(8),
                                child: Image.network(
                                  image,
                                  width: 36,
                                  height: 36,
                                  fit: BoxFit.cover,
                                  errorBuilder: (ctx, err, stack) => CircleAvatar(
                                    radius: 18,
                                    backgroundColor: Colors.blue.shade50,
                                    child: Text(icon ?? '${index + 1}', style: const TextStyle(fontSize: 16)),
                                  ),
                                ),
                              );
                            } else if (icon != null && icon.isNotEmpty) {
                              leadingWidget = CircleAvatar(
                                radius: 18,
                                backgroundColor: Colors.blue.shade50,
                                child: Text(icon, style: const TextStyle(fontSize: 18)),
                              );
                            } else {
                              leadingWidget = CircleAvatar(
                                radius: 18,
                                backgroundColor: Colors.blue.shade50,
                                child: Text(
                                  '${index + 1}',
                                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: Colors.blue.shade700),
                                ),
                              );
                            }

                            return CheckboxListTile(
                              secondary: leadingWidget,
                              title: Text(
                                catName,
                                style: TextStyle(
                                  fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                                ),
                              ),
                              subtitle: Text(
                                '#${index + 1} tartib raqam',
                                style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                              ),
                              value: isSelected,
                              activeColor: Colors.blue,
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
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                            ),
                            child: _saving
                                ? const SizedBox(
                                    height: 20,
                                    width: 20,
                                    child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                                  )
                                : const Text('Saqlash va Davom etish', style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
    );
  }
}
