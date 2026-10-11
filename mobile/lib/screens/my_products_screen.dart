import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import '../api/api_client.dart';
import 'package:intl/intl.dart';
import 'edit_product_screen.dart';
import 'add_product_screen.dart';

class MyProductsScreen extends StatefulWidget {
  final bool isTab;
  const MyProductsScreen({super.key, this.isTab = false});

  @override
  State<MyProductsScreen> createState() => _MyProductsScreenState();
}

class _MyProductsScreenState extends State<MyProductsScreen> {
  List<dynamic> _products = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _fetchProducts();
  }

  Future<void> _fetchProducts() async {
    try {
      final resp = await apiClient.dio.get('/mobile/marketplace/products');
      if (mounted) {
        setState(() {
          _products = resp.data['items'] ?? [];
          _loading = false;
        });
      }
    } on DioException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.response?.data['detail'] ?? 'Xatolik yuz berdi')),
        );
        setState(() => _loading = false);
      }
    }
  }

  Color _getStatusColor(String status) {
    switch (status) {
      case 'draft': return Colors.grey;
      case 'review': return Colors.orange;
      case 'approved': return const Color(0xFF10B981);
      case 'rejected': return Colors.red;
      default: return Colors.blue;
    }
  }

  String _getStatusText(String status) {
    switch (status) {
      case 'draft': return 'Qoralama';
      case 'review': return 'Kutilmoqda';
      case 'approved': return 'Tasdiqlangan';
      case 'rejected': return 'Rad etilgan';
      default: return status;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text('Mening Mahsulotlarim', style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: Colors.white,
        elevation: 0,
        automaticallyImplyLeading: !widget.isTab,
        actions: [
          IconButton(
            icon: const Icon(Icons.add_circle_outline, color: Color(0xFF2563EB)),
            tooltip: 'Yangi mahsulot qo\'shish',
            onPressed: () async {
              final res = await Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const AddProductScreen()),
              );
              if (res == true) _fetchProducts();
            },
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Yangilash',
            onPressed: () {
              setState(() => _loading = true);
              _fetchProducts();
            },
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFF2563EB)))
          : _products.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.inventory_2_outlined, size: 64, color: Color(0xFF94A3B8)),
                      const SizedBox(height: 16),
                      const Text(
                        'Hozircha mahsulot qo\'shilmagan',
                        style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Color(0xFF475569)),
                      ),
                      const SizedBox(height: 12),
                      ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF2563EB),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                        ),
                        onPressed: () async {
                          final res = await Navigator.of(context).push(
                            MaterialPageRoute(builder: (_) => const AddProductScreen()),
                          );
                          if (res == true) _fetchProducts();
                        },
                        icon: const Icon(Icons.add, color: Colors.white),
                        label: const Text('Mahsulot qo\'shish', style: TextStyle(color: Colors.white)),
                      ),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _fetchProducts,
                  child: ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    itemCount: _products.length,
                    itemBuilder: (context, index) {
                      final product = _products[index];
                      final images = product['images'] as List<dynamic>? ?? [];
                      final price = NumberFormat.currency(locale: 'uz_UZ', symbol: 'so\'m', decimalDigits: 0).format(product['price']);
                      final status = product['status'] ?? 'draft';
                      final qty = (product['qty'] as num?)?.toDouble() ?? 0.0;
                      final qtyDisplay = qty.truncateToDouble() == qty ? qty.toInt().toString() : qty.toString();
                      final barcode = product['barcode']?.toString();
                      final categoryName = product['category_name']?.toString();

                      return Card(
                        margin: const EdgeInsets.symmetric(vertical: 6),
                        elevation: 0,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                          side: const BorderSide(color: Color(0xFFE2E8F0)),
                        ),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(14),
                          onTap: () async {
                            final res = await Navigator.of(context).push(
                              MaterialPageRoute(builder: (_) => EditProductScreen(product: product)),
                            );
                            if (res == true) _fetchProducts();
                          },
                          child: Padding(
                            padding: const EdgeInsets.all(12.0),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                // Product Image
                                ClipRRect(
                                  borderRadius: BorderRadius.circular(10),
                                  child: images.isNotEmpty
                                      ? Image.network(
                                          images[0],
                                          width: 76,
                                          height: 76,
                                          fit: BoxFit.cover,
                                          errorBuilder: (c, e, s) => Container(
                                            width: 76,
                                            height: 76,
                                            color: const Color(0xFFF1F5F9),
                                            child: const Icon(Icons.image, size: 36, color: Color(0xFF94A3B8)),
                                          ),
                                        )
                                      : Container(
                                          width: 76,
                                          height: 76,
                                          color: const Color(0xFFF1F5F9),
                                          child: const Icon(Icons.image_not_supported, size: 36, color: Color(0xFF94A3B8)),
                                        ),
                                ),
                                const SizedBox(width: 12),

                                // Product Info
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      // Title & Category
                                      Text(
                                        product['name'] ?? 'Nomsiz',
                                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15, color: Color(0xFF0F172A)),
                                        maxLines: 2,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                      if (categoryName != null && categoryName.isNotEmpty) ...[
                                        const SizedBox(height: 2),
                                        Text(
                                          categoryName,
                                          style: const TextStyle(fontSize: 11, color: Color(0xFF64748B), fontWeight: FontWeight.w500),
                                        ),
                                      ],
                                      const SizedBox(height: 6),

                                      // Price
                                      Text(
                                        price,
                                        style: const TextStyle(color: Color(0xFF10B981), fontWeight: FontWeight.w800, fontSize: 14),
                                      ),
                                      const SizedBox(height: 6),

                                      // Stock Qoldiq (User requested: mahsulotdan qancha qolganini ko'rsatsin!)
                                      Row(
                                        children: [
                                          Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                            decoration: BoxDecoration(
                                              color: qty > 0 ? const Color(0xFFEFF6FF) : const Color(0xFFFEF2F2),
                                              borderRadius: BorderRadius.circular(6),
                                              border: Border.all(
                                                color: qty > 0 ? const Color(0xFFBFDBFE) : const Color(0xFFFECACA),
                                              ),
                                            ),
                                            child: Row(
                                              mainAxisSize: MainAxisSize.min,
                                              children: [
                                                Icon(
                                                  Icons.inventory_2,
                                                  size: 13,
                                                  color: qty > 0 ? const Color(0xFF2563EB) : Colors.red,
                                                ),
                                                const SizedBox(width: 4),
                                                Text(
                                                  'Qoldiq: $qtyDisplay dona',
                                                  style: TextStyle(
                                                    fontSize: 11,
                                                    fontWeight: FontWeight.w700,
                                                    color: qty > 0 ? const Color(0xFF1D4ED8) : Colors.red,
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                          const SizedBox(width: 6),
                                          // Status Chip
                                          Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                                            decoration: BoxDecoration(
                                              color: _getStatusColor(status).withValues(alpha: 0.12),
                                              borderRadius: BorderRadius.circular(6),
                                              border: Border.all(color: _getStatusColor(status).withValues(alpha: 0.5)),
                                            ),
                                            child: Text(
                                              _getStatusText(status),
                                              style: TextStyle(
                                                fontSize: 11,
                                                fontWeight: FontWeight.w700,
                                                color: _getStatusColor(status),
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),

                                      // Barcode if present
                                      if (barcode != null && barcode.isNotEmpty) ...[
                                        const SizedBox(height: 4),
                                        Text(
                                          'Shtrix-kod: $barcode',
                                          style: const TextStyle(fontSize: 11, color: Color(0xFF94A3B8)),
                                        ),
                                      ],

                                      // Rejection reason if any
                                      if (status == 'rejected' && product['reject_reason'] != null) ...[
                                        const SizedBox(height: 4),
                                        Text(
                                          'Sabab: ${product['reject_reason']}',
                                          style: const TextStyle(color: Colors.red, fontSize: 11, fontWeight: FontWeight.w600),
                                        ),
                                      ],
                                    ],
                                  ),
                                ),

                                // Edit button
                                IconButton(
                                  icon: const Icon(Icons.edit_outlined, color: Color(0xFF2563EB), size: 20),
                                  tooltip: 'Tahrirlash',
                                  onPressed: () async {
                                    final res = await Navigator.of(context).push(
                                      MaterialPageRoute(builder: (_) => EditProductScreen(product: product)),
                                    );
                                    if (res == true) _fetchProducts();
                                  },
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
    );
  }
}
