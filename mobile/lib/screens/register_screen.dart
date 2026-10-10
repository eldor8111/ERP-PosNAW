import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'package:mask_text_input_formatter/mask_text_input_formatter.dart';
import '../api/api_client.dart';
import 'home_screen.dart';
import 'dart:io' show Platform;

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _orgCodeCtrl = TextEditingController();
  final _nameCtrl = TextEditingController();
  final _phoneCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  bool _loading = false;
  String _error = '';

  final _phoneFormatter = MaskTextInputFormatter(
    mask: '+998 (##) ###-##-##',
    filter: {"#": RegExp(r'[0-9]')},
    type: MaskAutoCompletionType.lazy,
  );

  Future<void> _register() async {
    final unmaskedPhone = _phoneFormatter.getUnmaskedText();
    if (unmaskedPhone.length != 9) {
      setState(() {
        _error = 'Telefon raqam noto\'g\'ri formatda';
      });
      return;
    }

    if (_orgCodeCtrl.text.isEmpty || _nameCtrl.text.isEmpty || _passwordCtrl.text.isEmpty) {
      setState(() {
        _error = 'Barcha maydonlarni to\'ldiring';
      });
      return;
    }

    setState(() {
      _loading = true;
      _error = '';
    });

    try {
      // 1. Send OTP code
      final sendRes = await apiClient.dio.post('/mobile/marketplace/register/send-code', data: {
        'org_code': _orgCodeCtrl.text.trim(),
        'phone': '998$unmaskedPhone',
      });
      final debugCode = sendRes.data['debug_code']?.toString();

      if (!mounted) return;
      // 2. Show OTP dialog
      final code = await showDialog<String>(
        context: context,
        barrierDismissible: false,
        builder: (context) => _OtpDialog(phone: '+998 $unmaskedPhone', debugCode: debugCode),
      );

      if (code != null && code.isNotEmpty) {
        // 3. Register with OTP
        setState(() => _loading = true);
        final response = await apiClient.dio.post('/mobile/marketplace/register', data: {
          'org_code': _orgCodeCtrl.text.trim(),
          'name': _nameCtrl.text.trim(),
          'phone': '998$unmaskedPhone',
          'sms_code': code,
          'password': _passwordCtrl.text,
          'device_id': 'device_dummy_123',
          'platform': Platform.operatingSystem,
          'app_version': '1.0.0',
        });

        // Automatically login on successful register
        final token = response.data['access_token'];
        if (token != null) {
          await apiClient.saveToken(token);
          if (!mounted) return;
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text("Ro'yxatdan muvaffaqiyatli o'tdingiz!")),
          );
          Navigator.of(context).pushAndRemoveUntil(
            MaterialPageRoute(builder: (_) => const HomeScreen()),
            (route) => false,
          );
        }
      }
    } on DioException catch (e) {
      setState(() {
        final detail = e.response?.data != null ? e.response?.data['detail'] : null;
        _error = detail is List ? (detail.isNotEmpty ? detail.first['msg'].toString() : 'Validation xatosi') : (detail?.toString() ?? 'Xatolik yuz berdi (${e.message})');
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Ro\'yxatdan o\'tish'),
        centerTitle: true,
        elevation: 0,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 32.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Logo placeholder
              Center(
                child: Column(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: Colors.blue.withOpacity(0.1),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(Icons.all_inclusive, size: 64, color: Colors.blue),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'Universal ERP',
                      style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.bold,
                        color: Colors.blue,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 48),
              TextField(
                controller: _orgCodeCtrl,
                decoration: InputDecoration(
                  labelText: 'Korxona kodi (Org Code)',
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                  prefixIcon: const Icon(Icons.business),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _nameCtrl,
                decoration: InputDecoration(
                  labelText: 'Ismingiz',
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                  prefixIcon: const Icon(Icons.person),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _phoneCtrl,
                inputFormatters: [_phoneFormatter],
                keyboardType: TextInputType.phone,
                decoration: InputDecoration(
                  labelText: 'Telefon raqam',
                  hintText: '+998 (__) ___-__-__',
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                  prefixIcon: const Icon(Icons.phone),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _passwordCtrl,
                obscureText: true,
                decoration: InputDecoration(
                  labelText: 'Parol',
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                  prefixIcon: const Icon(Icons.lock),
                ),
              ),
              if (_error.isNotEmpty) ...[
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.red.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    _error, 
                    style: const TextStyle(color: Colors.red, fontWeight: FontWeight.bold),
                    textAlign: TextAlign.center,
                  ),
                ),
              ],
              const SizedBox(height: 32),
              SizedBox(
                height: 54,
                child: ElevatedButton(
                  onPressed: _loading ? null : _register,
                  style: ElevatedButton.styleFrom(
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: _loading 
                      ? const SizedBox(height: 24, width: 24, child: CircularProgressIndicator(strokeWidth: 2)) 
                      : const Text('Ro\'yxatdan o\'tish', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _OtpDialog extends StatefulWidget {
  final String phone;
  final String? debugCode;
  const _OtpDialog({required this.phone, this.debugCode});

  @override
  State<_OtpDialog> createState() => _OtpDialogState();
}

class _OtpDialogState extends State<_OtpDialog> {
  late final TextEditingController _codeCtrl;

  @override
  void initState() {
    super.initState();
    _codeCtrl = TextEditingController(text: widget.debugCode ?? '');
  }

  @override
  void dispose() {
    _codeCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Kodni tasdiqlash'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('${widget.phone} raqamiga tasdiqlash kodi yuborildi. Iltimos kodni kiriting:'),
          if (widget.debugCode != null) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.blue.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                'Tasdiqlash kodi: ${widget.debugCode}',
                style: const TextStyle(color: Colors.blue, fontWeight: FontWeight.bold),
              ),
            ),
          ],
          const SizedBox(height: 16),
          TextField(
            controller: _codeCtrl,
            keyboardType: TextInputType.number,
            maxLength: 6,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 24, letterSpacing: 8),
            decoration: InputDecoration(
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Bekor qilish'),
        ),
        ElevatedButton(
          onPressed: () {
            if (_codeCtrl.text.trim().length >= 4) {
              Navigator.of(context).pop(_codeCtrl.text.trim());
            }
          },
          child: const Text('Tasdiqlash'),
        ),
      ],
    );
  }
}
