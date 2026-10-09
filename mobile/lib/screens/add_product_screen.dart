import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:dio/dio.dart';
import '../api/api_client.dart';

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
  bool _loading = true;
  bool _saving = false;
  
  final List<File> _images = [];
  final ImagePicker _picker = ImagePicker();

  @override
  void initState() {
    super.initState();
    _fetchMyCategories();
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

  Future<void> _pickImage(ImageSource source) async {
    if (_images.length >= 8) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Maksimal 8 ta rasm qo\'shish mumkin')));
      return;
    }
    final picked = await _picker.pickImage(source: source, imageQuality: 70);
    if (picked != null) {
      setState(() {
        _images.add(File(picked.path));
      });
    }
  }

  Future<void> _submitProduct(bool asSubmit) async {
    if (_nameCtrl.text.isEmpty || _priceCtrl.text.isEmpty || _selectedCategoryId == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Nomi, narxi va kategoriyasi kiritilishi shart')));
      return;
    }

    setState(() => _saving = true);
    try {
      // 1. Upload images (In a real app, upload via a separate endpoint and get URLs back)
      // Here we mock the URLs for demonstration since we don't have a direct file upload endpoint defined yet in backend API tz.
      List<String> imageUrls = [];
      // For this step, if there was an upload API:
      // for (var img in _images) { 
      //    FormData formData = FormData.fromMap({'file': await MultipartFile.fromFile(img.path)});
      //    var res = await apiClient.dio.post('/mobile/marketplace/upload', data: formData);
      //    imageUrls.add(res.data['url']);
      // }
      
      // 2. Submit product
      await apiClient.dio.post('/mobile/marketplace/products', data: {
        'name': _nameCtrl.text.trim(),
        'price': double.tryParse(_priceCtrl.text) ?? 0,
        'qty': double.tryParse(_qtyCtrl.text) ?? 0,
        'category_id': _selectedCategoryId,
        'description': _descCtrl.text.trim(),
        'barcode': _barcodeCtrl.text.trim(),
        'images': imageUrls, // Emulated
        'submit': asSubmit,
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
      appBar: AppBar(title: const Text('Mahsulot qo\'shish')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Images section
            SizedBox(
              height: 100,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: [
                  InkWell(
                    onTap: () {
                      showModalBottomSheet(context: context, builder: (_) => SafeArea(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            ListTile(
                              leading: const Icon(Icons.camera_alt), title: const Text('Kameradan'),
                              onTap: () { Navigator.pop(context); _pickImage(ImageSource.camera); },
                            ),
                            ListTile(
                              leading: const Icon(Icons.photo_library), title: const Text('Galereyadan'),
                              onTap: () { Navigator.pop(context); _pickImage(ImageSource.gallery); },
                            ),
                          ],
                        ),
                      ));
                    },
                    child: Container(
                      width: 100,
                      decoration: BoxDecoration(color: Colors.grey.shade200, borderRadius: BorderRadius.circular(8)),
                      child: const Icon(Icons.add_a_photo, size: 40, color: Colors.grey),
                    ),
                  ),
                  const SizedBox(width: 8),
                  ..._images.map((img) => Padding(
                    padding: const EdgeInsets.only(right: 8.0),
                    child: Stack(
                      children: [
                        ClipRRect(
                          borderRadius: BorderRadius.circular(8),
                          child: Image.file(img, width: 100, height: 100, fit: BoxFit.cover),
                        ),
                        Positioned(
                          right: 4, top: 4,
                          child: InkWell(
                            onTap: () => setState(() => _images.remove(img)),
                            child: const CircleAvatar(radius: 12, backgroundColor: Colors.white, child: Icon(Icons.close, size: 16, color: Colors.red)),
                          ),
                        ),
                      ],
                    ),
                  )),
                ],
              ),
            ),
            const SizedBox(height: 16),
            
            // Form fields
            DropdownButtonFormField<int>(
              initialValue: _selectedCategoryId,
              decoration: const InputDecoration(labelText: 'Kategoriya', border: OutlineInputBorder()),
              items: _myCategories.map((c) => DropdownMenuItem<int>(
                value: c['id'],
                child: Text(c['name']),
              )).toList(),
              onChanged: (val) => setState(() => _selectedCategoryId = val),
            ),
            const SizedBox(height: 16),
            TextField(controller: _nameCtrl, decoration: const InputDecoration(labelText: 'Mahsulot nomi', border: OutlineInputBorder())),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(child: TextField(controller: _priceCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Narxi', border: OutlineInputBorder()))),
                const SizedBox(width: 16),
                Expanded(child: TextField(controller: _qtyCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Qoldiq (Soni/Kg)', border: OutlineInputBorder()))),
              ],
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _barcodeCtrl,
              decoration: InputDecoration(
                labelText: 'Shtrix kod',
                border: const OutlineInputBorder(),
                suffixIcon: IconButton(
                  icon: const Icon(Icons.qr_code_scanner),
                  onPressed: () {
                    // Integration with barcode_scan2 or similar would go here
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Skaner ulanmoqda...')));
                  },
                ),
              ),
            ),
            const SizedBox(height: 16),
            TextField(controller: _descCtrl, maxLines: 4, decoration: const InputDecoration(labelText: 'Tavsif', border: OutlineInputBorder())),
            const SizedBox(height: 32),
            
            // Action buttons
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: _saving ? null : () => _submitProduct(false),
                    style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
                    child: const Text('Qoralama'),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: ElevatedButton(
                    onPressed: _saving ? null : () => _submitProduct(true),
                    style: ElevatedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
                    child: _saving ? const CircularProgressIndicator() : const Text('Tasdiqqa yuborish'),
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
