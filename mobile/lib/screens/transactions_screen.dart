import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import '../api/api_client.dart';
import 'package:intl/intl.dart';

class TransactionsScreen extends StatefulWidget {
  const TransactionsScreen({super.key});

  @override
  State<TransactionsScreen> createState() => _TransactionsScreenState();
}

class _TransactionsScreenState extends State<TransactionsScreen> {
  List<dynamic> _transactions = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _fetchTransactions();
  }

  Future<void> _fetchTransactions() async {
    try {
      final resp = await apiClient.dio.get('/mobile/marketplace/transactions');
      setState(() {
        _transactions = resp.data['items'] ?? [];
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Balans va Tarix')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _transactions.isEmpty
              ? const Center(child: Text('Tranzaksiyalar mavjud emas.'))
              : RefreshIndicator(
                  onRefresh: _fetchTransactions,
                  child: ListView.builder(
                    padding: const EdgeInsets.all(8.0),
                    itemCount: _transactions.length,
                    itemBuilder: (context, index) {
                      final txn = _transactions[index];
                      final type = txn['type']; // income, payout, commission
                      final amount = NumberFormat.currency(locale: 'uz_UZ', symbol: 'so\'m').format(txn['amount']);
                      
                      final isIncome = type == 'income';
                      final color = isIncome ? Colors.green : Colors.red;
                      final icon = isIncome ? Icons.arrow_downward : Icons.arrow_upward;
                      
                      String title = 'Tranzaksiya';
                      if (type == 'income') title = 'Savdodan tushum';
                      if (type == 'payout') title = 'Pul yechib olindi (To\'lov)';
                      if (type == 'commission') title = 'Tizim komissiyasi';

                      final date = DateTime.tryParse(txn['created_at'] ?? '');
                      final dateStr = date != null ? DateFormat('dd.MM.yyyy HH:mm').format(date.toLocal()) : '';

                      return Card(
                        margin: const EdgeInsets.symmetric(vertical: 6, horizontal: 8),
                        child: ListTile(
                          leading: CircleAvatar(
                            backgroundColor: color.withOpacity(0.1),
                            child: Icon(icon, color: color),
                          ),
                          title: Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
                          subtitle: Text(dateStr),
                          trailing: Text(
                            '${isIncome ? '+' : '-'}$amount',
                            style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 16),
                          ),
                        ),
                      );
                    },
                  ),
                ),
    );
  }
}
