import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import '../api/api_client.dart';
import 'package:intl/intl.dart';

class MyProductsScreen extends StatefulWidget {
  const MyProductsScreen({super.key});

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
      setState(() {
        _products = resp.data['items'] ?? [];
        _loading = false;
      });
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
      case 'approved': return Colors.green;
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
      appBar: AppBar(title: const Text('Mening Mahsulotlarim')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _products.isEmpty
              ? const Center(child: Text('Hozircha mahsulot qo\'shilmagan.'))
              : RefreshIndicator(
                  onRefresh: _fetchProducts,
                  child: ListView.builder(
                    padding: const EdgeInsets.all(8.0),
                    itemCount: _products.length,
                    itemBuilder: (context, index) {
                      final product = _products[index];
                      final images = product['images'] as List<dynamic>? ?? [];
                      final price = NumberFormat.currency(locale: 'uz_UZ', symbol: 'so\'m').format(product['price']);
                      final status = product['status'] ?? 'draft';

                      return Card(
                        margin: const EdgeInsets.symmetric(vertical: 8, horizontal: 8),
                        child: ListTile(
                          contentPadding: const EdgeInsets.all(12),
                          leading: images.isNotEmpty
                              ? ClipRRect(
                                  borderRadius: BorderRadius.circular(8),
                                  child: Image.network(
                                    images[0],
                                    width: 60,
                                    height: 60,
                                    fit: BoxFit.cover,
                                    errorBuilder: (c, e, s) => const Icon(Icons.image, size: 60),
                                  ),
                                )
                              : const Icon(Icons.image_not_supported, size: 60),
                          title: Text(product['name'] ?? 'Nomsiz', style: const TextStyle(fontWeight: FontWeight.bold)),
                          subtitle: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const SizedBox(height: 4),
                              Text(price, style: const TextStyle(color: Colors.green, fontWeight: FontWeight.bold)),
                              const SizedBox(height: 4),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                decoration: BoxDecoration(
                                  color: _getStatusColor(status).withOpacity(0.1),
                                  borderRadius: BorderRadius.circular(4),
                                  border: Border.all(color: _getStatusColor(status)),
                                ),
                                child: Text(
                                  _getStatusText(status),
                                  style: TextStyle(fontSize: 12, color: _getStatusColor(status)),
                                ),
                              ),
                              if (status == 'rejected' && product['reject_reason'] != null)
                                Padding(
                                  padding: const EdgeInsets.only(top: 4.0),
                                  child: Text(
                                    'Sabab: ${product['reject_reason']}',
                                    style: const TextStyle(color: Colors.red, fontSize: 12),
                                  ),
                                ),
                            ],
                          ),
                          onTap: () {
                            // Optionally open product details for editing if it's draft or rejected
                          },
                        ),
                      );
                    },
                  ),
                ),
    );
  }
}
