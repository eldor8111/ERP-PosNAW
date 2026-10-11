import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:dio/dio.dart';
import '../api/api_client.dart';

class EditProductScreen extends StatefulWidget {
  final Map<String, dynamic> product;

  const EditProductScreen({super.key, required this.product});

  @override
  State<EditProductScreen> createState() => _EditProductScreenState();
}

class _EditProductScreenState extends State<EditProductScreen> {
  late final TextEditingController _nameCtrl;
  late final TextEditingController _priceCtrl;
  late final TextEditingController _qtyCtrl;
  late final TextEditingController _descCtrl;
  late final TextEditingController _barcodeCtrl;

  int? _selectedCategoryId;
  String _selectedCategoryName = '';
  List<dynamic> _myCategories = [];
  bool _loading = true;
  bool _saving = false;
  bool _removeBg = true;

  final List<String> _existingImages = [];
  final List<File> _newImages = [];
  final ImagePicker _picker = ImagePicker();

  static const brandBlue = Color(0xFF2563EB);

  @override
  void initState() {
    super.initState();
    final p = widget.product;
    _nameCtrl = TextEditingController(text: p['name'] ?? '');
    _priceCtrl = TextEditingController(text: (p['price'] ?? 0).toString());
    _qtyCtrl = TextEditingController(text: (p['qty'] ?? 0).toString());
    _descCtrl = TextEditingController(text: p['description'] ?? '');
    _barcodeCtrl = TextEditingController(text: p['barcode'] ?? '');

    _selectedCategoryId = p['category_id'] as int?;
    _selectedCategoryName = p['category_name'] ?? '';

    final imgs = p['images'] as List<dynamic>? ?? [];
    for (var img in imgs) {
      if (img is String && img.isNotEmpty) {
        _existingImages.add(img);
      }
    }

    _fetchCategories();
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _priceCtrl.dispose();
    _qtyCtrl.dispose();
    _descCtrl.dispose();
    _barcodeCtrl.dispose();
    super.dispose();
  }

  Future<void> _fetchCategories() async {
    try {
      final resp = await apiClient.dio.get('/mobile/marketplace/me');
      final cats = resp.data['categories'] as List<dynamic>? ?? [];
      setState(() {
        _myCategories = cats;
        if (_selectedCategoryName.isEmpty && _selectedCategoryId != null) {
          final found = cats.firstWhere((c) => c['id'] == _selectedCategoryId, orElse: () => null);
          if (found != null) {
            _selectedCategoryName = found['name'] ?? '';
          }
        }
        _loading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pickImage(ImageSource source) async {
    if (_existingImages.length + _newImages.length >= 8) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Maksimal 8 ta rasm yuklash mumkin')),
      );
      return;
    }
    final picked = await _picker.pickImage(source: source, imageQuality: 75);
    if (picked != null) {
      setState(() {
        _newImages.add(File(picked.path));
      });
    }
  }

  Future<void> _saveProduct() async {
    if (_nameCtrl.text.trim().isEmpty || _priceCtrl.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Nomi va narxini kiritish shart')),
      );
      return;
    }

    final isApproved = widget.product['status'] == 'approved';
    if (isApproved) {
      final confirm = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Qayta tasdiqlash so\'rovi'),
          content: const Text(
            'Ushbu mahsulot tasdiqlangan. Narx, qoldiq yoki ma\'lumotlar o\'zgartirilsa, korxona adminiga qayta tekshirish uchun so\'rov yuboriladi.\n\nDavom etasizmi?',
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Bekor qilish')),
            ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: brandBlue),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('So\'rov yuborish', style: TextStyle(color: Colors.white)),
            ),
          ],
        ),
      );
      if (confirm != true) return;
    }

    setState(() => _saving = true);
    try {
      // 1. Yangi rasmlarni yuklash
      List<String> finalImages = List.from(_existingImages);
      for (var img in _newImages) {
        final filename = img.path.split('/').last.split('\\').last;
        final formData = FormData.fromMap({
          'file': await MultipartFile.fromFile(img.path, filename: filename),
        });
        final res = await apiClient.dio.post(
          '/mobile/marketplace/upload',
          queryParameters: {'remove_bg': _removeBg},
          data: formData,
        );
        if (res.data != null && res.data['url'] != null) {
          finalImages.add(res.data['url']);
        }
      }

      // 2. PUT so'rovi yuborish
      final productId = widget.product['id'];
      await apiClient.dio.put('/mobile/marketplace/products/$productId', data: {
        'name': _nameCtrl.text.trim(),
        'price': double.tryParse(_priceCtrl.text) ?? 0,
        'qty': double.tryParse(_qtyCtrl.text) ?? 0,
        'category_id': _selectedCategoryId,
        'description': _descCtrl.text.trim(),
        'barcode': _barcodeCtrl.text.trim(),
        'images': finalImages,
        'submit': true,
      });

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            isApproved
                ? 'Tahrirlash so\'rovi korxona rahbariga yuborildi!'
                : 'Mahsulot muvaffaqiyatli yangilandi!',
          ),
        ),
      );
      Navigator.of(context).pop(true);
    } on DioException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.response?.data['detail'] ?? 'Xatolik yuz berdi')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator(color: brandBlue)));
    }

    final status = widget.product['status'] ?? 'draft';

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text('Mahsulotni tahrirlash', style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: Colors.white,
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Status notice
            if (status == 'approved')
              Container(
                padding: const EdgeInsets.all(12),
                margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(
                  color: const Color(0xFFEFF6FF),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFFBFDBFE)),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.info_outline, color: brandBlue, size: 20),
                    SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        'Tasdiqlangan mahsulot: narx yoki qoldiq o\'zgarsa, korxona adminiga qayta so\'rov yuboriladi.',
                        style: TextStyle(fontSize: 12, color: Color(0xFF1E3A8A), fontWeight: FontWeight.w500),
                      ),
                    ),
                  ],
                ),
              ),

            // Images row
            const Text(
              'RASMLAR (MAKSIMAL 8 TA)',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: Color(0xFF475569), letterSpacing: 0.6),
            ),
            const SizedBox(height: 8),

            SizedBox(
              height: 100,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: [
                  InkWell(
                    onTap: () {
                      showModalBottomSheet(
                        context: context,
                        builder: (_) => SafeArea(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              ListTile(
                                leading: const Icon(Icons.camera_alt, color: brandBlue),
                                title: const Text('Kameradan rasmga olish'),
                                onTap: () {
                                  Navigator.pop(context);
                                  _pickImage(ImageSource.camera);
                                },
                              ),
                              ListTile(
                                leading: const Icon(Icons.photo_library, color: brandBlue),
                                title: const Text('Galereyadan tanlash'),
                                onTap: () {
                                  Navigator.pop(context);
                                  _pickImage(ImageSource.gallery);
                                },
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                    child: Container(
                      width: 90,
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: const Color(0xFFCBD5E1), style: BorderStyle.solid),
                      ),
                      child: const Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.add_a_photo, color: brandBlue, size: 28),
                          SizedBox(height: 4),
                          Text('Qo\'shish', style: TextStyle(fontSize: 11, color: brandBlue, fontWeight: FontWeight.w600)),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),

                  // Existing server images
                  ..._existingImages.map((url) => Padding(
                        padding: const EdgeInsets.only(right: 8.0),
                        child: Stack(
                          children: [
                            ClipRRect(
                              borderRadius: BorderRadius.circular(12),
                              child: Image.network(
                                url,
                                width: 90,
                                height: 90,
                                fit: BoxFit.cover,
                                errorBuilder: (ctx, err, stack) => Container(
                                  width: 90,
                                  height: 90,
                                  color: Colors.grey.shade200,
                                  child: const Icon(Icons.broken_image),
                                ),
                              ),
                            ),
                            Positioned(
                              top: 4,
                              right: 4,
                              child: InkWell(
                                onTap: () => setState(() => _existingImages.remove(url)),
                                child: const CircleAvatar(
                                  radius: 11,
                                  backgroundColor: Colors.white,
                                  child: Icon(Icons.close, size: 14, color: Colors.red),
                                ),
                              ),
                            ),
                          ],
                        ),
                      )),

                  // Newly added files
                  ..._newImages.map((file) => Padding(
                        padding: const EdgeInsets.only(right: 8.0),
                        child: Stack(
                          children: [
                            ClipRRect(
                              borderRadius: BorderRadius.circular(12),
                              child: Image.file(file, width: 90, height: 90, fit: BoxFit.cover),
                            ),
                            Positioned(
                              top: 4,
                              right: 4,
                              child: InkWell(
                                onTap: () => setState(() => _newImages.remove(file)),
                                child: const CircleAvatar(
                                  radius: 11,
                                  backgroundColor: Colors.white,
                                  child: Icon(Icons.close, size: 14, color: Colors.red),
                                ),
                              ),
                            ),
                          ],
                        ),
                      )),
                ],
              ),
            ),

            const SizedBox(height: 12),

            // Background removal switch
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.auto_fix_high, color: brandBlue, size: 20),
                  const SizedBox(width: 10),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Fonni tozalash (Oq fon)', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
                        Text('Marketplace uchun rasmni toza oq fonga keltiradi', style: TextStyle(fontSize: 11, color: Color(0xFF64748B))),
                      ],
                    ),
                  ),
                  Switch(
                    value: _removeBg,
                    activeThumbColor: brandBlue,
                    onChanged: (v) => setState(() => _removeBg = v),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 18),

            // Kategoriya tanlash
            const Text(
              'KATEGORIYA',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: Color(0xFF475569), letterSpacing: 0.6),
            ),
            const SizedBox(height: 6),
            DropdownButtonFormField<int>(
              initialValue: _selectedCategoryId,
              decoration: InputDecoration(
                filled: true,
                fillColor: Colors.white,
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
                enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
              ),
              items: _myCategories.map((c) {
                return DropdownMenuItem<int>(
                  value: c['id'] as int,
                  child: Text(c['name'] ?? '', style: const TextStyle(fontSize: 14)),
                );
              }).toList(),
              onChanged: (val) {
                setState(() => _selectedCategoryId = val);
              },
            ),

            const SizedBox(height: 16),

            // Name
            const Text(
              'MAHSULOT NOMI',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: Color(0xFF475569), letterSpacing: 0.6),
            ),
            const SizedBox(height: 6),
            TextField(
              controller: _nameCtrl,
              decoration: InputDecoration(
                filled: true,
                fillColor: Colors.white,
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
                enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
              ),
            ),

            const SizedBox(height: 16),

            // Price & Quantity
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'NARXI (SO\'M)',
                        style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: Color(0xFF475569), letterSpacing: 0.6),
                      ),
                      const SizedBox(height: 6),
                      TextField(
                        controller: _priceCtrl,
                        keyboardType: TextInputType.number,
                        decoration: InputDecoration(
                          filled: true,
                          fillColor: Colors.white,
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
                          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'QOLDIQ (DONA/KG)',
                        style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: Color(0xFF475569), letterSpacing: 0.6),
                      ),
                      const SizedBox(height: 6),
                      TextField(
                        controller: _qtyCtrl,
                        keyboardType: TextInputType.number,
                        decoration: InputDecoration(
                          filled: true,
                          fillColor: Colors.white,
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
                          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),

            const SizedBox(height: 16),

            // Barcode
            const Text(
              'SHTRIX-KOD',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: Color(0xFF475569), letterSpacing: 0.6),
            ),
            const SizedBox(height: 6),
            TextField(
              controller: _barcodeCtrl,
              decoration: InputDecoration(
                filled: true,
                fillColor: Colors.white,
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
                enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
              ),
            ),

            const SizedBox(height: 16),

            // Description
            const Text(
              'TAVSIF',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: Color(0xFF475569), letterSpacing: 0.6),
            ),
            const SizedBox(height: 6),
            TextField(
              controller: _descCtrl,
              maxLines: 3,
              decoration: InputDecoration(
                filled: true,
                fillColor: Colors.white,
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
                enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
              ),
            ),

            const SizedBox(height: 28),

            // Save Button
            SizedBox(
              height: 52,
              child: ElevatedButton(
                onPressed: _saving ? null : _saveProduct,
                style: ElevatedButton.styleFrom(
                  backgroundColor: brandBlue,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  elevation: 0,
                ),
                child: _saving
                    ? const CircularProgressIndicator(color: Colors.white)
                    : Text(
                        status == 'approved' ? 'So\'rovni yuborish' : 'Saqlash',
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
