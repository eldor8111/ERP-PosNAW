import 'package:flutter/material.dart';

class ECodeLogoWidget extends StatelessWidget {
  final double size;
  final bool showText;

  const ECodeLogoWidget({
    super.key,
    this.size = 56,
    this.showText = true,
  });

  @override
  Widget build(BuildContext context) {
    final logoIcon = CustomPaint(
      size: Size(size, size),
      painter: _ECodeLogoPainter(),
    );

    if (!showText) return logoIcon;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        logoIcon,
        const SizedBox(height: 12),
        Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Text(
              'E-CODE ',
              style: TextStyle(
                fontSize: size * 0.42,
                fontWeight: FontWeight.w900,
                color: const Color(0xFF1E293B),
                letterSpacing: 1.2,
              ),
            ),
            Text(
              'ERP',
              style: TextStyle(
                fontSize: size * 0.42,
                fontWeight: FontWeight.w900,
                color: const Color(0xFF2563EB),
                letterSpacing: 1.2,
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          'Marketplace Agent',
          style: TextStyle(
            fontSize: size * 0.22,
            fontWeight: FontWeight.w600,
            color: const Color(0xFF64748B),
            letterSpacing: 0.5,
          ),
        ),
      ],
    );
  }
}

class _ECodeLogoPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final scale = size.width / 60.0;

    final paint1 = Paint()
      ..color = const Color(0xFF1E293B)
      ..strokeWidth = 5.0 * scale
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    final paint2 = Paint()
      ..color = const Color(0xFF2563EB)
      ..strokeWidth = 5.0 * scale
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    final paint3 = Paint()
      ..color = const Color(0xFF3B82F6)
      ..strokeWidth = 5.0 * scale
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    // Left U
    final path1 = Path();
    path1.moveTo(13 * scale, 12 * scale);
    path1.lineTo(13 * scale, 36 * scale);
    path1.arcToPoint(
      Offset(21 * scale, 36 * scale),
      radius: Radius.circular(4 * scale),
      clockwise: false,
    );
    path1.lineTo(21 * scale, 12 * scale);
    canvas.drawPath(path1, paint1);

    // Middle U (offset downwards)
    final path2 = Path();
    path2.moveTo(26 * scale, 20 * scale);
    path2.lineTo(26 * scale, 44 * scale);
    path2.arcToPoint(
      Offset(34 * scale, 44 * scale),
      radius: Radius.circular(4 * scale),
      clockwise: false,
    );
    path2.lineTo(34 * scale, 20 * scale);
    canvas.drawPath(path2, paint2);

    // Right U
    final path3 = Path();
    path3.moveTo(39 * scale, 12 * scale);
    path3.lineTo(39 * scale, 36 * scale);
    path3.arcToPoint(
      Offset(47 * scale, 36 * scale),
      radius: Radius.circular(4 * scale),
      clockwise: false,
    );
    path3.lineTo(47 * scale, 12 * scale);
    canvas.drawPath(path3, paint3);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
