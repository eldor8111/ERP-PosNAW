import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:dio/dio.dart';
import '../api/api_client.dart';
import '../widgets/barcode_scanner_dialog.dart';

class AddProductScreen extends StatefulWidget {
  const AddProductScreen({super.key});

  @override
  State<AddProductScreen> createState() => _AddProductScreenState();
}

class _AddProductScreenState extends State<AddProductScreen> {
  final _nameCtrl = TextEditingController();
  final _priceCtrl = TextEditingController();
  final _qtyCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  final _barcodeCtrl = TextEditingController();
  
  int? _selectedCategoryId;
  List<dynamic> _myCategories = [];
  // T3.17: topshirish ombori (ixtiyoriy) — faqat korxonada 2+ filial bo'lsa server ro'yxat qaytaradi
  int? _preferredWarehouseId;
  List<dynamic> _warehouses = [];
  bool _loading = true;
  bool _saving = false;
  bool _removeBg = true;
  bool _isUploadingImage = false;
  
  final List<String> _imageUrls = [];
  final ImagePicker _picker = ImagePicker();

  static const brandBlue = Color(0xFF2563EB);

  @override
  void initState() {
    super.initState();
    _fetchMyCategories();
    _fetchWarehouses();
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

  Future<void> _fetchMyCategories() async {
    try {
      final resp = await apiClient.dio.get('/mobile/marketplace/me');
      setState(() {
        _myCategories = resp.data['categories'] ?? [];
        if (_myCategories.isNotEmpty) {
          _selectedCategoryId = _myCategories[0]['id'];
        }
        _loading = false;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Xatolik: $e')));
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _fetchWarehouses() async {
    try {
      final resp = await apiClient.dio.get('/mobile/marketplace/warehouses');
      if (!mounted) return;
      setState(() => _warehouses = (resp.data is List) ? resp.data : []);
    } catch (_) {
      // Ixtiyoriy funksiya: xato bo'lsa dropdown ko'rsatilmaydi
    }
  }

  Future<void> _pickImage(ImageSource source) async {
    if (_imageUrls.length >= 8) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Maksimal 8 ta rasm qo\'shish mumkin')));
      return;
    }
    final picked = await _picker.pickImage(source: source, imageQuality: 85);
    if (picked == null) return;

    setState(() => _isUploadingImage = true);
    try {
      final filename = picked.path.split('/').last.split('\\').last;
      final formData = FormData.fromMap({
        'file': await MultipartFile.fromFile(picked.path, filename: filename),
      });
      final res = await apiClient.dio.post(
        '/mobile/marketplace/upload',
        queryParameters: {'remove_bg': _removeBg},
        data: formData,
      );
      if (res.data != null && res.data['url'] != null) {
        final url = res.data['url'] as String;
        final bgRemoved = res.data['bg_removed'] == true;
        setState(() {
          _imageUrls.add(url);
        });
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(bgRemoved ? 'Rasm yuklandi va foni olib tashlandi (Oq fon)!' : 'Rasm yuklandi!'),
              backgroundColor: bgRemoved ? const Color(0xFF10B981) : brandBlue,
              duration: const Duration(seconds: 2),
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Rasm yuklashda xatolik: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isUploadingImage = false);
    }
  }

  void _generateRandomBarcode() {
    final now = DateTime.now().millisecondsSinceEpoch.toString();
    final base = '200${now.substring(now.length - 9)}';
    int sum = 0;
    for (int i = 0; i < 12; i++) {
      int digit = int.parse(base[i]);
      sum += (i % 2 == 0) ? digit : digit * 3;
    }
    int check = (10 - (sum % 10)) % 10;
    final ean13 = '$base$check';
    setState(() => _barcodeCtrl.text = ean13);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Yangi shtrix-kod yaratildi: $ean13'), duration: const Duration(seconds: 2)),
    );
  }

  Future<void> _submitProduct(bool asSubmit) async {
    if (_nameCtrl.text.isEmpty || _priceCtrl.text.isEmpty || _selectedCategoryId == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Nomi, narxi va kategoriyasi kiritilishi shart')));
      return;
    }

    setState(() => _saving = true);
    try {
      await apiClient.dio.post('/mobile/marketplace/products', data: {
        'name': _nameCtrl.text.trim(),
        'price': double.tryParse(_priceCtrl.text) ?? 0,
        'qty': double.tryParse(_qtyCtrl.text) ?? 0,
        'category_id': _selectedCategoryId,
        'description': _descCtrl.text.trim(),
        'barcode': _barcodeCtrl.text.trim(),
        'images': _imageUrls,
        'submit': asSubmit,
        if (_preferredWarehouseId != null) 'preferred_warehouse_id': _preferredWarehouseId,
      });

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(asSubmit ? 'Mahsulot tekshiruvga yuborildi!' : 'Qoralama saqlandi')),
      );
      Navigator.of(context).pop(true);
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
    if (_loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text('Mahsulot qo\'shish', style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: Colors.white,
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Images section (Immediate Live Preview on White BG)
            SizedBox(
              height: 110,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: [
                  // Add Image Button
                  InkWell(
                    onTap: _isUploadingImage ? null : () {
                      showModalBottomSheet(context: context, builder: (_) => SafeArea(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            ListTile(
                              leading: const Icon(Icons.camera_alt, color: brandBlue),
                              title: const Text('Kameradan rasmga olish'),
                              onTap: () { Navigator.pop(context); _pickImage(ImageSource.camera); },
                            ),
                            ListTile(
                              leading: const Icon(Icons.photo_library, color: brandBlue),
                              title: const Text('Galereyadan tanlash'),
                              onTap: () { Navigator.pop(context); _pickImage(ImageSource.gallery); },
                            ),
                          ],
                        ),
                      ));
                    },
                    child: Container(
                      width: 100,
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: const Color(0xFFCBD5E1)),
                      ),
                      child: const Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.add_a_photo, size: 30, color: brandBlue),
                          SizedBox(height: 6),
                          Text('Rasm qo\'shish', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: brandBlue)),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),

                  // Uploading loader tile
                  if (_isUploadingImage)
                    Container(
                      width: 110,
                      margin: const EdgeInsets.only(right: 10),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: const Color(0xFF93C5FD)),
                      ),
                      child: const Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          SizedBox(
                            width: 24,
                            height: 24,
                            child: CircularProgressIndicator(strokeWidth: 2.5, color: brandBlue),
                          ),
                          SizedBox(height: 8),
                          Text(
                            'Fon tozalanmoqda...',
                            textAlign: TextAlign.center,
                            style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Color(0xFF1D4ED8)),
                          ),
                        ],
                      ),
                    ),

                  // Clean images on White BG preview
                  ..._imageUrls.map((url) => Padding(
                    padding: const EdgeInsets.only(right: 10.0),
                    child: Stack(
                      children: [
                        Container(
                          width: 100,
                          height: 110,
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: const Color(0xFFE2E8F0)),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.04),
                                blurRadius: 4,
                                offset: const Offset(0, 2),
                              ),
                            ],
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(12),
                            child: Image.network(
                              url,
                              width: 100,
                              height: 110,
                              fit: BoxFit.contain,
                              loadingBuilder: (c, child, progress) {
                                if (progress == null) return child;
                                return const Center(child: CircularProgressIndicator(strokeWidth: 2));
                              },
                              errorBuilder: (c, e, s) => const Icon(Icons.broken_image, size: 36, color: Colors.grey),
                            ),
                          ),
                        ),
                        Positioned(
                          left: 4,
                          bottom: 4,
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                            decoration: BoxDecoration(
                              color: const Color(0xFF10B981),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: const Text('Oq fon ✓', style: TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.w700)),
                          ),
                        ),
                        Positioned(
                          right: 4,
                          top: 4,
                          child: InkWell(
                            onTap: () => setState(() => _imageUrls.remove(url)),
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
            const SizedBox(height: 16),
            
            // Form fields
            DropdownButtonFormField<int>(
              initialValue: _selectedCategoryId,
              decoration: InputDecoration(
                labelText: 'Kategoriya',
                filled: true,
                fillColor: Colors.white,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
              items: _myCategories.map((c) => DropdownMenuItem<int>(
                value: c['id'],
                child: Text(c['name']),
              )).toList(),
              onChanged: (val) => setState(() => _selectedCategoryId = val),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _nameCtrl,
              decoration: InputDecoration(
                labelText: 'Mahsulot nomi',
                filled: true,
                fillColor: Colors.white,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _priceCtrl,
                    keyboardType: TextInputType.number,
                    decoration: InputDecoration(
                      labelText: 'Narxi (so\'m)',
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: TextField(
                    controller: _qtyCtrl,
                    keyboardType: TextInputType.number,
                    decoration: InputDecoration(
                      labelText: 'Qoldiq (Soni/Kg)',
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Barcode with Camera Scan & Auto EAN Generator
            TextField(
              controller: _barcodeCtrl,
              decoration: InputDecoration(
                labelText: 'Shtrix-kod (EAN / QR)',
                hintText: 'Skanerlang yoki avto yarating',
                filled: true,
                fillColor: Colors.white,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                suffixIcon: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextButton.icon(
                      onPressed: _generateRandomBarcode,
                      icon: const Icon(Icons.bolt, size: 16, color: brandBlue),
                      label: const Text('Avto', style: TextStyle(fontWeight: FontWeight.bold, color: brandBlue, fontSize: 12)),
                    ),
                    IconButton(
                      icon: const Icon(Icons.qr_code_scanner, color: brandBlue),
                      tooltip: 'Kameradan skanerlash',
                      onPressed: () async {
                        final code = await BarcodeScannerDialog.scan(context);
                        if (code != null && code.isNotEmpty) {
                          setState(() => _barcodeCtrl.text = code);
                        }
                      },
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            if (_warehouses.isNotEmpty) ...[
              DropdownButtonFormField<int?>(
                initialValue: _preferredWarehouseId,
                isExpanded: true,
                decoration: InputDecoration(
                  labelText: 'Topshirish ombori (ixtiyoriy)',
                  filled: true,
                  fillColor: Colors.white,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                ),
                items: [
                  const DropdownMenuItem<int?>(value: null, child: Text('Tanlanmagan (admin belgilaydi)')),
                  ..._warehouses.map((w) => DropdownMenuItem<int?>(
                    value: w['id'] as int,
                    child: Text(
                      w['branch_name'] != null ? '${w['name']} — ${w['branch_name']}' : '${w['name']}',
                      overflow: TextOverflow.ellipsis,
                    ),
                  )),
                ],
                onChanged: (val) => setState(() => _preferredWarehouseId = val),
              ),
              const SizedBox(height: 16),
            ],
            TextField(
              controller: _descCtrl,
              maxLines: 4,
              decoration: InputDecoration(
                labelText: 'Tavsif',
                filled: true,
                fillColor: Colors.white,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
            const SizedBox(height: 32),
            
            // Action buttons
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: _saving ? null : () => _submitProduct(false),
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                    child: const Text('Qoralama'),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: ElevatedButton(
                    onPressed: _saving ? null : () => _submitProduct(true),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: brandBlue,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                    child: _saving ? const CircularProgressIndicator(color: Colors.white) : const Text('Tasdiqqa yuborish', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
