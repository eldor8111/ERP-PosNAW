"""Rol guruhlari (backend). Frontend `constants/roles.js` bilan mos.

Hisobot/moliya/dashboard routerlari rol konstantalarini shu yerdan import qiladi (T2.1) — har
faylda takrorlanmaydi. `super_admin` `require_roles` da avtomatik o'tadi.
"""
from app.models.user import UserRole

# Hisobotlar: /reports/*, /sales-report/*, /finance-report/*
REPORT_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.super_admin)

# Moliya: /finance/*
FINANCE_ROLES = (UserRole.admin, UserRole.director, UserRole.accountant, UserRole.manager)

# Rahbar dashboardlari: /dashboard/summary, /mobile/dashboard/*, /reports/dashboard
DASHBOARD_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant)
