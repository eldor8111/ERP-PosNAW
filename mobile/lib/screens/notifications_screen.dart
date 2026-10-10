import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import '../api/api_client.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  List<dynamic> _items = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _fetchNotifications();
  }

  Future<void> _fetchNotifications() async {
    try {
      final res = await apiClient.dio.get('/mobile/marketplace/notifications');
      setState(() {
        _items = res.data['items'] ?? [];
        _loading = false;
      });
    } on DioException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.response?.data['detail'] ?? 'Yuklashda xatolik')),
        );
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _markAllRead() async {
    try {
      await apiClient.dio.post('/mobile/marketplace/notifications/read-all');
      setState(() {
        for (var item in _items) {
          item['is_read'] = true;
        }
      });
    } catch (_) {}
  }

  Future<void> _markRead(int id, int index) async {
    try {
      await apiClient.dio.post('/mobile/marketplace/notifications/$id/read');
      setState(() {
        _items[index]['is_read'] = true;
      });
    } catch (_) {}
  }

  IconData _getIcon(String type) {
    switch (type) {
      case 'order_sold':
        return Icons.shopping_bag;
      case 'product_approved':
        return Icons.verified;
      case 'product_rejected':
        return Icons.error_outline;
      case 'payment_received':
        return Icons.account_balance_wallet;
      default:
        return Icons.notifications;
    }
  }

  Color _getColor(String type) {
    switch (type) {
      case 'order_sold':
        return Colors.green;
      case 'product_approved':
        return Colors.blue;
      case 'product_rejected':
        return Colors.red;
      case 'payment_received':
        return Colors.teal;
      default:
        return Colors.orange;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Bildirishnomalar'),
        actions: [
          if (_items.isNotEmpty)
            IconButton(
              icon: const Icon(Icons.done_all),
              tooltip: 'Barchasini o\'qilgan qilish',
              onPressed: _markAllRead,
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _items.isEmpty
              ? const Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.notifications_off_outlined, size: 64, color: Colors.grey),
                      SizedBox(height: 16),
                      Text('Bildirishnomalar mavjud emas', style: TextStyle(fontSize: 16, color: Colors.grey)),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _fetchNotifications,
                  child: ListView.separated(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    itemCount: _items.length,
                    separatorBuilder: (ctx, i) => const Divider(height: 1),
                    itemBuilder: (context, index) {
                      final item = _items[index];
                      final isRead = item['is_read'] == true;
                      final type = item['type'] ?? 'general';
                      final title = item['title'] ?? '';
                      final body = item['body'] ?? '';
                      final createdAt = item['created_at'] != null
                          ? item['created_at'].toString().split('T').first
                          : '';

                      return Container(
                        color: isRead ? Colors.transparent : Colors.blue.shade50.withValues(alpha: 0.5),
                        child: ListTile(
                          onTap: () {
                            if (!isRead) {
                              _markRead(item['id'] as int, index);
                            }
                          },
                          leading: CircleAvatar(
                            backgroundColor: _getColor(type).withValues(alpha: 0.15),
                            child: Icon(_getIcon(type), color: _getColor(type)),
                          ),
                          title: Row(
                            children: [
                              Expanded(
                                child: Text(
                                  title,
                                  style: TextStyle(
                                    fontWeight: isRead ? FontWeight.w600 : FontWeight.bold,
                                  ),
                                ),
                              ),
                              if (!isRead)
                                Container(
                                  width: 8,
                                  height: 8,
                                  decoration: const BoxDecoration(
                                    color: Colors.blue,
                                    shape: BoxShape.circle,
                                  ),
                                ),
                            ],
                          ),
                          subtitle: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const SizedBox(height: 4),
                              Text(body, style: const TextStyle(fontSize: 13, color: Colors.black87)),
                              const SizedBox(height: 4),
                              Text(createdAt, style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
    );
  }
}
