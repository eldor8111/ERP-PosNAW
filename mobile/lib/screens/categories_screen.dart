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
  List<dynamic> _treeCategories = [];
  Set<int> _selectedIds = {};
  bool _loading = true;
  bool _saving = false;
  String _searchQuery = '';
  final TextEditingController _searchCtrl = TextEditingController();

  static const brandBlue = Color(0xFF2563EB);

  @override
  void initState() {
    super.initState();
    _fetchData();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _fetchData() async {
    try {
      final catResp = await apiClient.dio.get('/mobile/marketplace/categories');
      final profileResp = await apiClient.dio.get('/mobile/marketplace/me');

      final currentCats = profileResp.data['categories'] as List<dynamic>? ?? [];
      final preselected = currentCats.map<int>((c) => c['id'] as int).toSet();

      final items = catResp.data['items'] as List<dynamic>? ?? [];
      final tree = catResp.data['tree'] as List<dynamic>? ?? [];

      setState(() {
        _allCategories = items;
        _treeCategories = tree.isNotEmpty ? tree : _buildTreeFromFlat(items);
        _selectedIds = preselected;
        _loading = false;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Kategoriyalarni yuklashda xatolik: $e')),
        );
        setState(() => _loading = false);
      }
    }
  }

  List<dynamic> _buildTreeFromFlat(List<dynamic> items) {
    Map<int, Map<String, dynamic>> map = {};
    for (var it in items) {
      map[it['id']] = {...it, 'children': <dynamic>[]};
    }
    List<dynamic> roots = [];
    for (var it in items) {
      final pid = it['parent_id'];
      if (pid != null && map.containsKey(pid)) {
        (map[pid]!['children'] as List).add(map[it['id']]);
      } else {
        roots.add(map[it['id']]);
      }
    }
    return roots;
  }

  void _collectAllIds(dynamic node, Set<int> result) {
    if (node == null) return;
    if (node['id'] != null) result.add(node['id'] as int);
    final children = node['children'] as List<dynamic>?;
    if (children != null) {
      for (var c in children) {
        _collectAllIds(c, result);
      }
    }
  }

  void _toggleGroup(dynamic groupNode, bool selectAll) {
    final ids = <int>{};
    _collectAllIds(groupNode, ids);
    setState(() {
      if (selectAll) {
        _selectedIds.addAll(ids);
      } else {
        _selectedIds.removeAll(ids);
      }
    });
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
        Navigator.of(context).pop(true);
      }
    } on DioException catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.response?.data['detail'] ?? 'Xatolik yuz berdi')),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _buildGroupTile(dynamic parent) {
    final parentId = parent['id'] as int;
    final parentName = parent['name'] ?? 'Kategoriya';
    final children = parent['children'] as List<dynamic>? ?? [];

    final groupIds = <int>{};
    _collectAllIds(parent, groupIds);
    final selectedCountInGroup = groupIds.where((id) => _selectedIds.contains(id)).length;
    final isAllSelected = groupIds.isNotEmpty && selectedCountInGroup == groupIds.length;
    final isPartiallySelected = selectedCountInGroup > 0 && !isAllSelected;

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: isAllSelected ? brandBlue.withValues(alpha: 0.5) : const Color(0xFFE2E8F0)),
      ),
      child: ExpansionTile(
        key: PageStorageKey('cat_$parentId'),
        initiallyExpanded: _searchQuery.isNotEmpty,
        leading: Checkbox(
          value: isAllSelected ? true : (isPartiallySelected ? null : false),
          tristate: true,
          activeColor: brandBlue,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
          onChanged: (val) {
            _toggleGroup(parent, val == true);
          },
        ),
        title: Text(
          parentName,
          style: TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w700,
            color: selectedCountInGroup > 0 ? brandBlue : const Color(0xFF0F172A),
          ),
        ),
        subtitle: Text(
          children.isEmpty ? 'To\'g\'ridan-to\'g\'ri bo\'lim' : '${children.length} ta ichki bo\'lim ($selectedCountInGroup tanlandi)',
          style: const TextStyle(fontSize: 12, color: Color(0xFF64748B)),
        ),
        children: children.map<Widget>((child) {
          final childId = child['id'] as int;
          final childName = child['name'] ?? 'Noma\'lum';
          final subChildren = child['children'] as List<dynamic>? ?? [];
          final isSelected = _selectedIds.contains(childId);

          if (subChildren.isEmpty) {
            return Container(
              color: const Color(0xFFF8FAFC),
              child: CheckboxListTile(
                contentPadding: const EdgeInsets.only(left: 36, right: 16),
                dense: true,
                title: Text(childName, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500)),
                value: isSelected,
                activeColor: brandBlue,
                onChanged: (val) {
                  setState(() {
                    if (val == true) {
                      _selectedIds.add(childId);
                    } else {
                      _selectedIds.remove(childId);
                    }
                  });
                },
              ),
            );
          }

          // Nabira kategoriyalar bo'lsa
          return Container(
            color: const Color(0xFFF8FAFC),
            child: ExpansionTile(
              dense: true,
              leading: Checkbox(
                value: isSelected,
                activeColor: brandBlue,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
                onChanged: (val) {
                  setState(() {
                    if (val == true) {
                      _selectedIds.add(childId);
                    } else {
                      _selectedIds.remove(childId);
                    }
                  });
                },
              ),
              title: Text(childName, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
              children: subChildren.map<Widget>((sub) {
                final subId = sub['id'] as int;
                final subName = sub['name'] ?? '';
                final isSubSelected = _selectedIds.contains(subId);
                return Container(
                  color: Colors.white,
                  child: CheckboxListTile(
                    contentPadding: const EdgeInsets.only(left: 54, right: 16),
                    dense: true,
                    title: Text(subName, style: const TextStyle(fontSize: 13)),
                    value: isSubSelected,
                    activeColor: brandBlue,
                    onChanged: (val) {
                      setState(() {
                        if (val == true) {
                          _selectedIds.add(subId);
                        } else {
                          _selectedIds.remove(subId);
                        }
                      });
                    },
                  ),
                );
              }).toList(),
            ),
          );
        }).toList(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final allSelected = _allCategories.isNotEmpty && _selectedIds.length == _allCategories.length;

    // Filter categories by search
    final filteredTree = _searchQuery.isEmpty
        ? _treeCategories
        : _treeCategories.where((c) {
            final name = (c['name'] ?? '').toString().toLowerCase();
            if (name.contains(_searchQuery.toLowerCase())) return true;
            final children = c['children'] as List<dynamic>? ?? [];
            return children.any((sub) {
              final subName = (sub['name'] ?? '').toString().toLowerCase();
              return subName.contains(_searchQuery.toLowerCase());
            });
          }).toList();

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text('Kategoriyalar (Mir-Maza)', style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: Colors.white,
        elevation: 0,
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
                style: const TextStyle(fontWeight: FontWeight.bold, color: brandBlue),
              ),
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: brandBlue))
          : Column(
              children: [
                // Search Bar
                Container(
                  color: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                  child: TextField(
                    controller: _searchCtrl,
                    onChanged: (v) => setState(() => _searchQuery = v.trim()),
                    decoration: InputDecoration(
                      hintText: 'Kategoriyalarni qidirish (500+ ta bo\'lim)...',
                      hintStyle: const TextStyle(fontSize: 13, color: Color(0xFF94A3B8)),
                      prefixIcon: const Icon(Icons.search, color: brandBlue, size: 20),
                      suffixIcon: _searchQuery.isNotEmpty
                          ? IconButton(
                              icon: const Icon(Icons.clear, size: 18),
                              onPressed: () {
                                _searchCtrl.clear();
                                setState(() => _searchQuery = '');
                              },
                            )
                          : null,
                      filled: true,
                      fillColor: const Color(0xFFF1F5F9),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: BorderSide.none,
                      ),
                    ),
                  ),
                ),

                // Info Header
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Row(
                    children: [
                      const Icon(Icons.info_outline, size: 16, color: brandBlue),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          'Ota bo\'limni bosib barchasini tanlashingiz mumkin (${_selectedIds.length} ta tanlandi)',
                          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF475569)),
                        ),
                      ),
                    ],
                  ),
                ),

                // Categories Tree List
                Expanded(
                  child: RefreshIndicator(
                    onRefresh: _fetchData,
                    color: brandBlue,
                    child: filteredTree.isEmpty
                        ? const Center(child: Text('Kategoriyalar topilmadi'))
                        : ListView.builder(
                            padding: const EdgeInsets.only(bottom: 90),
                            itemCount: filteredTree.length,
                            itemBuilder: (context, index) {
                              return _buildGroupTile(filteredTree[index]);
                            },
                          ),
                  ),
                ),
              ],
            ),
      bottomSheet: Container(
        padding: const EdgeInsets.all(16.0),
        decoration: BoxDecoration(
          color: Colors.white,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 10,
              offset: const Offset(0, -4),
            ),
          ],
        ),
        child: SizedBox(
          width: double.infinity,
          height: 50,
          child: ElevatedButton(
            onPressed: _saving ? null : _saveCategories,
            style: ElevatedButton.styleFrom(
              backgroundColor: brandBlue,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
              elevation: 0,
            ),
            child: _saving
                ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                : Text(
                    'Saqlash (${_selectedIds.length} ta tanlandi)',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                  ),
          ),
        ),
      ),
    );
  }
}
